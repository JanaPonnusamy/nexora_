"""Sync scheduler tick (SYNC-SCHED-01).

This is the piece that was missing entirely: something that reads
dbo.sync_schedule on a timer, decides which stores are due, and turns that
into dbo.sync_execution rows -- while guaranteeing one active sync per store
and a configurable global concurrency cap. See scheduler_repository.py for
the per-store locking and scheduler_time.py for the missed-schedule /
grid-alignment math; this module is the orchestration + logging around them.

Configuration follows the same convention already used everywhere else in
this backend (config/database.py, api/app.py CORS): plain environment
variables with sane defaults, not a new bespoke settings system.
"""
import datetime as _dt
import os
import threading

from config.database import get_connection
from repositories.sync_admin_repository import SyncAdminRepository
from modules.sync import scheduler_repository as repo
from modules.sync.scheduler_time import current_grid_slot

MAX_CONCURRENT_SYNCS = int(os.getenv("NEXORA_SYNC_MAX_CONCURRENT", "2"))
TICK_SECONDS = int(os.getenv("NEXORA_SYNC_TICK_SECONDS", "30"))

_last_tick = {"at": None, "summary": None, "error": None}
_stop_event = threading.Event()
_thread = None


def _log(line):
    """Best-effort log line that can never raise -- a logging failure must
    never be able to break the scheduler loop."""
    try:
        print(line, flush=True)
    except Exception:
        pass


def get_status():
    """For a diagnostics endpoint: proves the scheduler is alive and shows
    what its last pass actually did, instead of asking the operator to trust
    that a thread exists somewhere."""
    return {
        "max_concurrent_syncs": MAX_CONCURRENT_SYNCS,
        "tick_seconds": TICK_SECONDS,
        "worker_id": repo.WORKER_ID,
        "last_tick_at": _last_tick["at"].isoformat() if _last_tick["at"] else None,
        "last_tick_summary": _last_tick["summary"],
        "last_tick_error": _last_tick["error"],
    }


def run_tick():
    """One scheduler pass. Safe to call on a timer from any number of backend
    worker processes: acquire_tick_lock() ensures only one of them actually
    does anything on a given tick -- the others return immediately.

    Everything, including opening the connection, is inside the try/except:
    a transient DB outage (SQL Server restart, network blip) must degrade to
    "this tick did nothing, try again next tick", never to an exception that
    escapes this function -- the caller is a daemon thread with no
    supervisor, so an uncaught exception here kills scheduling permanently
    until the whole backend process is restarted."""
    conn = None
    try:
        conn = get_connection()
        if not repo.acquire_tick_lock(conn):
            return {"ran": False, "reason": "tick already in progress on another worker"}
        try:
            summary = _run_tick_locked(conn)
            _last_tick["at"] = _dt.datetime.now()
            _last_tick["summary"] = summary
            _last_tick["error"] = None
            return summary
        finally:
            repo.release_tick_lock(conn)
    except Exception as ex:
        _last_tick["at"] = _dt.datetime.now()
        _last_tick["error"] = str(ex)
        _log("[SCHEDULER] Tick failed:\n" + _safe_tb())
        return {"ran": False, "error": str(ex)}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _safe_tb():
    import traceback
    try:
        return traceback.format_exc()
    except Exception:
        return "<traceback unavailable>"


def _run_tick_locked(conn):
    cur = conn.cursor()
    repo.ensure_schema(cur)
    # sync_schedule.interval_minutes lives in SyncAdminRepository's own
    # ensure_schema (the Schedule Plan CRUD's schema guard) -- needed here too
    # since this tick reads that column before the Schedule Plan API has
    # necessarily been hit once to create it.
    SyncAdminRepository().ensure_schema(cur)
    conn.commit()

    SyncAdminRepository()._reap_stale_executions(cur)

    created = repo.ensure_default_schedules(cur)
    conn.commit()
    if created:
        _log("[SCHEDULER] Seeded %d default 'Every 30 Minutes' schedule(s) for "
             "tenant(s) with no schedule configured" % created)

    schedules = repo.get_enabled_interval_schedules(cur)
    if not schedules:
        return {"ran": True, "schedules": 0, "claimed": 0, "queued": 0, "skipped": 0}

    active = repo.count_active_syncs(cur)
    remaining_slots = max(0, MAX_CONCURRENT_SYNCS - active)
    now = _dt.datetime.now()

    claimed = queued = skipped = 0
    for schedule in schedules:
        slot = current_grid_slot(schedule["interval_minutes"], now)
        if slot is None:
            continue
        stores = repo.resolve_stores(cur, schedule["tenant_id"], schedule["store_id"])
        for store in stores:
            has_slot = remaining_slots > 0
            try:
                result = repo.dispatch(schedule, store, slot, has_slot)
            except Exception:
                _log("[SYNC] Dispatch failed | Store: %s | Schedule: %s\n%s"
                     % (store["store_code"], schedule["schedule_name"], _safe_tb()))
                continue
            outcome = result["outcome"]
            if outcome == "ALREADY_HANDLED":
                continue  # this slot was already resolved by an earlier tick; stay quiet
            _log(
                "[SCHEDULER] Schedule triggered | Store: %s | Schedule: %s (every %s min) | "
                "Scheduled time: %s | Execution ID: %s"
                % (store["store_code"], schedule["schedule_name"], schedule["interval_minutes"],
                   slot, result.get("execution_id"))
            )
            if outcome == "CLAIMED":
                claimed += 1
                remaining_slots -= 1
                _log("[SYNC] Lock acquired | Store: %s | Execution ID: %s | Worker: %s"
                     % (store["store_code"], result["execution_id"], repo.WORKER_ID))
            elif outcome in ("QUEUED", "STILL_QUEUED"):
                queued += 1
                if outcome == "QUEUED":
                    _log("[SYNC] Queued - waiting for concurrency slot (max=%d) | Store: %s | Execution ID: %s"
                         % (MAX_CONCURRENT_SYNCS, store["store_code"], result["execution_id"]))
            elif outcome == "SKIPPED_ALREADY_RUNNING":
                skipped += 1
                _log("[SYNC] Skipped - Store already syncing | Store: %s | Existing Execution ID: %s"
                     % (store["store_code"], result.get("existing_execution_id")))
            elif outcome == "LOCK_CONTENDED":
                _log("[SYNC] Lock contended, will retry next tick | Store: %s" % store["store_code"])

    conn.commit()
    return {"ran": True, "schedules": len(schedules), "claimed": claimed,
            "queued": queued, "skipped": skipped}


def _loop():
    _log("[SCHEDULER] Background scheduler thread started | worker=%s | "
         "tick_seconds=%s | max_concurrent_syncs=%s"
         % (repo.WORKER_ID, TICK_SECONDS, MAX_CONCURRENT_SYNCS))
    while not _stop_event.is_set():
        # run_tick() already catches everything it can identify, but this is
        # a daemon thread with no supervisor -- belt and suspenders so that
        # literally nothing (a bug, a library raising something unexpected)
        # can ever take the loop down permanently the way a single uncaught
        # DB-connect error did in production on 2026-09-13.
        try:
            run_tick()
        except Exception:
            _last_tick["at"] = _dt.datetime.now()
            _last_tick["error"] = "loop caught: " + _safe_tb()
            _log("[SCHEDULER] Tick raised past run_tick() -- loop continues:\n" + _safe_tb())
        _stop_event.wait(TICK_SECONDS)
    _log("[SCHEDULER] Background scheduler thread stopped | worker=%s" % repo.WORKER_ID)


def start_background_loop():
    """Idempotent: calling this more than once (e.g. re-imported module in
    tests) never spawns a second thread."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="nexora-sync-scheduler", daemon=True)
    _thread.start()
    return _thread


def stop_background_loop():
    _stop_event.set()
