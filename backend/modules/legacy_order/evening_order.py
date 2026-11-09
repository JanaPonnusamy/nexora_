"""Evening (second) order: run Order Process for every chosen store, ONE
store at a time, from a set time each day (default 18:25), each followed by
Compare with that store's earlier order from today -- the owner's daily manual
"trigger all stores + compare", automated.

Settings live in central OrderNMC (dbo.LegacyOrderSchedule, one row per
schedule key) and are edited from the stock client's Legacy Order > Settings,
so the backend that owns that OrderNMC runs it and no PC has to stay open.
Two backends on the same OrderNMC can't both run it: each day's run is claimed
with one conditional UPDATE on LastRunDate.

Env:
  LEGACY_EVENING_ORDER_DISABLED=1          don't start the loop (temp/test backends)
  LEGACY_EVENING_ORDER_CATCHUP_MINUTES     a backend that was down at the start
                                           time still runs within this window
                                           (default 180)
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import time

from modules.legacy_order import database, repository

logger = logging.getLogger(__name__)

SCHEDULE_KEY = "EVENING"
DEFAULT_RUN_AT = "18:25"
POLL_SECONDS = 30
JOB_POLL_SECONDS = 5
JOB_TIMEOUT_SECONDS = 90 * 60

_SCHEMA_SQL = """
IF OBJECT_ID('dbo.LegacyOrderSchedule', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyOrderSchedule (
        ScheduleKey VARCHAR(32) NOT NULL PRIMARY KEY,
        Enabled BIT NOT NULL DEFAULT 0,
        RunAt CHAR(5) NOT NULL DEFAULT '18:25',
        Stores NVARCHAR(MAX) NULL,
        LastRunDate DATE NULL,
        LastRunStartedAt DATETIME2(0) NULL,
        LastRunFinishedAt DATETIME2(0) NULL,
        LastRunSummary NVARCHAR(MAX) NULL,
        UpdatedAt DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedBy NVARCHAR(128) NULL
    );
END;
"""

_started = False
_schema_ready = False
_start_lock = threading.Lock()
_run_lock = threading.Lock()


def catch_up_minutes():
    try:
        return max(0, int(os.getenv("LEGACY_EVENING_ORDER_CATCHUP_MINUTES", "180")))
    except ValueError:
        return 180


def parse_run_at(value):
    """'HH:MM' (24h) -> datetime.time; ValueError otherwise."""
    try:
        hours, minutes = str(value or "").strip().split(":")
        return datetime.time(int(hours), int(minutes))
    except (ValueError, TypeError):
        raise ValueError("Start time must be HH:MM (24-hour), e.g. 18:25.") from None


def is_due(now, run_at, last_run_date, catch_up):
    """True when today's run hasn't happened and now is within
    [start, start + catch_up minutes]."""
    start = datetime.datetime.combine(now.date(), parse_run_at(run_at))
    not_run_today = last_run_date is None or last_run_date < now.date()
    return not_run_today and start <= now <= start + datetime.timedelta(minutes=catch_up)


def next_run(now, enabled, run_at, last_run_date, catch_up):
    if not enabled:
        return None
    start = datetime.datetime.combine(now.date(), parse_run_at(run_at))
    not_run_today = last_run_date is None or last_run_date < now.date()
    if not_run_today and now <= start + datetime.timedelta(minutes=catch_up):
        return start
    return start + datetime.timedelta(days=1)


# ---- settings ---------------------------------------------------------------

def _ensure_schema(cur):
    global _schema_ready
    if not _schema_ready:
        cur.execute(_SCHEMA_SQL)
        cur.connection.commit()
        _schema_ready = True


def _read_row():
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_schema(cur)
        row = cur.execute(
            "SELECT Enabled, RunAt, Stores, LastRunDate, LastRunStartedAt, LastRunFinishedAt, "
            "LastRunSummary, UpdatedAt, UpdatedBy FROM dbo.LegacyOrderSchedule WHERE ScheduleKey = ?",
            SCHEDULE_KEY,
        ).fetchone()
    if not row:
        return {"enabled": False, "run_at": DEFAULT_RUN_AT, "stores": None, "last_run_date": None,
                "last_run_started_at": None, "last_run_finished_at": None, "last_run": None,
                "updated_at": None, "updated_by": None}
    last_run_date = row.LastRunDate
    if isinstance(last_run_date, str):
        last_run_date = datetime.date.fromisoformat(last_run_date[:10])
    try:
        last_run = json.loads(row.LastRunSummary) if row.LastRunSummary else None
    except ValueError:
        last_run = None
    return {
        "enabled": bool(row.Enabled),
        "run_at": str(row.RunAt or DEFAULT_RUN_AT).strip(),
        "stores": json.loads(row.Stores) if row.Stores else None,
        "last_run_date": last_run_date,
        "last_run_started_at": row.LastRunStartedAt,
        "last_run_finished_at": row.LastRunFinishedAt,
        "last_run": last_run,
        "updated_at": row.UpdatedAt,
        "updated_by": row.UpdatedBy,
    }


def get_schedule():
    sch = _read_row()
    nxt = next_run(datetime.datetime.now(), sch["enabled"], sch["run_at"], sch["last_run_date"], catch_up_minutes())
    return {**sch, "next_run": nxt, "running": _run_lock.locked(), "catch_up_minutes": catch_up_minutes()}


def set_schedule(enabled, run_at, stores, actor=None):
    """stores: list of OrderNMC StoreNames, or None for every active store.
    Saving after today's start time never fires straight away (the evening
    order may already have been run by hand): today counts as done and the
    first automatic run is the next day."""
    run_time = parse_run_at(run_at)
    run_at = run_time.strftime("%H:%M")
    if stores is not None:
        stores = sorted({str(s).strip() for s in stores if str(s).strip()})
        if enabled and not stores:
            raise ValueError("Pick at least one store for the evening order.")
    now = datetime.datetime.now()
    skip_today = bool(enabled) and now.time() >= run_time
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_schema(cur)
        stores_json = json.dumps(stores) if stores is not None else None
        cur.execute(
            "MERGE dbo.LegacyOrderSchedule AS t USING (SELECT ? AS ScheduleKey) AS s "
            "ON t.ScheduleKey = s.ScheduleKey "
            "WHEN MATCHED THEN UPDATE SET Enabled = ?, RunAt = ?, Stores = ?, UpdatedAt = SYSUTCDATETIME(), UpdatedBy = ?, "
            "  LastRunDate = CASE WHEN ? = 1 AND (t.LastRunDate IS NULL OR t.LastRunDate < ?) THEN ? ELSE t.LastRunDate END "
            "WHEN NOT MATCHED THEN INSERT (ScheduleKey, Enabled, RunAt, Stores, UpdatedBy, LastRunDate) "
            "  VALUES (?, ?, ?, ?, ?, CASE WHEN ? = 1 THEN ? ELSE NULL END);",
            SCHEDULE_KEY, 1 if enabled else 0, run_at, stores_json, actor,
            1 if skip_today else 0, now.date(), now.date(),
            SCHEDULE_KEY, 1 if enabled else 0, run_at, stores_json, actor, 1 if skip_today else 0, now.date(),
        )
        conn.commit()
    return get_schedule()


# ---- running -----------------------------------------------------------------

def _claim_today(now, force=False):
    """Mark today's evening run as taken. force=True (Run now) claims it even
    if it already ran; otherwise only one claim per day across every backend
    on this OrderNMC succeeds."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_schema(cur)
        if force:
            cur.execute(
                "MERGE dbo.LegacyOrderSchedule AS t USING (SELECT ? AS ScheduleKey) AS s "
                "ON t.ScheduleKey = s.ScheduleKey "
                "WHEN MATCHED THEN UPDATE SET LastRunDate = ?, LastRunStartedAt = ?, LastRunFinishedAt = NULL, LastRunSummary = NULL "
                "WHEN NOT MATCHED THEN INSERT (ScheduleKey, LastRunDate, LastRunStartedAt) VALUES (?, ?, ?);",
                SCHEDULE_KEY, now.date(), now, SCHEDULE_KEY, now.date(), now,
            )
            claimed = True
        else:
            cur.execute(
                "UPDATE dbo.LegacyOrderSchedule SET LastRunDate = ?, LastRunStartedAt = ?, "
                "LastRunFinishedAt = NULL, LastRunSummary = NULL "
                "WHERE ScheduleKey = ? AND Enabled = 1 AND (LastRunDate IS NULL OR LastRunDate < ?)",
                now.date(), now, SCHEDULE_KEY, now.date(),
            )
            claimed = cur.rowcount == 1
        conn.commit()
    return claimed


def _save_summary(summary, finished):
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.LegacyOrderSchedule SET LastRunSummary = ?, "
            "LastRunFinishedAt = CASE WHEN ? = 1 THEN ? ELSE NULL END WHERE ScheduleKey = ?",
            json.dumps(summary, default=str), 1 if finished else 0, datetime.datetime.now(), SCHEDULE_KEY,
        )
        conn.commit()


def target_stores(configured):
    """Active stores, limited to the configured list (None = all active stores
    of whichever tenant the active context already points at -- see
    router._scope_tenant / service._resolve_store; there's no single
    multi-tenant store list so an unscoped call only ever sees one tenant)."""
    active = [s["store_name"] for s in repository.list_stores(True)]
    if configured is None:
        return active
    wanted = {str(s).strip().upper() for s in configured}
    return [s for s in active if s.strip().upper() in wanted]


def _wait_for_job(job_id):
    from modules.legacy_order import service

    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if not job or job["status"] != "running":
            return job
        time.sleep(JOB_POLL_SECONDS)
    return service.get_job(job_id)


def run_stores(stores, trigger):
    """Order Process for each store, one after another, with the store's saved
    Compare mode (NONE = the plain .73-style order). Both Order Process
    warnings are acknowledged (nobody is there to click them)."""
    from modules.legacy_order import service

    summary = {"trigger": trigger, "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "stores": [], "finished_at": None}
    for name in stores:
        entry = {"store_name": name, "status": "running"}
        summary["stores"].append(entry)
        _save_summary(summary, finished=False)
        try:
            job_id = service.start_order_process(name, confirmed_stale_order=True)
            entry["job_id"] = job_id
            job = _wait_for_job(job_id) or {}
            result = job.get("result") or {}
            entry.update(
                status=job.get("status") or "lost",
                rows=result.get("rows"),
                compare=result.get("compare"),
                error=job.get("error"),
            )
        except Exception as exc:  # running job, unreachable branch, DB down ...
            logger.warning("[EVENING_ORDER] %s not run: %s", name, exc)
            entry.update(status="skipped", error=str(exc))
    summary["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    _save_summary(summary, finished=True)
    logger.info("[EVENING_ORDER] %s run finished: %s", trigger,
                {e["store_name"]: e["status"] for e in summary["stores"]})
    return summary


def _run_guarded(stores, trigger):
    if not _run_lock.acquire(blocking=False):
        return False
    try:
        run_stores(stores, trigger)
    except Exception:
        logger.exception("[EVENING_ORDER] run failed")
    finally:
        _run_lock.release()
    return True


def run_now():
    """'Run now' from Settings: starts in the background and counts as
    today's evening run (so the timed run doesn't regenerate again)."""
    if _run_lock.locked():
        raise ValueError("The evening order is already running.")
    sch = _read_row()
    stores = target_stores(sch["stores"])
    if not stores:
        raise ValueError("No active store is selected for the evening order.")
    _claim_today(datetime.datetime.now(), force=True)
    threading.Thread(target=_run_guarded, args=(stores, "manual"), name="legacy-evening-order-now",
                     daemon=True).start()
    return {"started": True, "stores": stores}


def tick(now=None):
    """One scheduler check; returns True when it ran the evening order."""
    now = now or datetime.datetime.now()
    sch = _read_row()
    if not sch["enabled"] or _run_lock.locked():
        return False
    if not is_due(now, sch["run_at"], sch["last_run_date"], catch_up_minutes()):
        return False
    if not _claim_today(now):
        return False  # another backend on this OrderNMC already took today's run
    stores = target_stores(sch["stores"])
    logger.info("[EVENING_ORDER] starting for %s", stores)
    return _run_guarded(stores, "schedule")


def _loop():
    time.sleep(60)  # let the backend finish starting first
    last_error_logged = 0.0
    while True:
        try:
            tick()
        except Exception:
            # OrderNMC down etc.: log at most every 30 minutes, keep checking.
            if time.monotonic() - last_error_logged > 1800:
                last_error_logged = time.monotonic()
                logger.exception("[EVENING_ORDER] check failed")
        time.sleep(POLL_SECONDS)


def start_background_loop():
    global _started
    if os.getenv("LEGACY_EVENING_ORDER_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return False
    with _start_lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, name="legacy-evening-order", daemon=True).start()
    print("[EVENING_ORDER] scheduler started (settings: Legacy Order > Settings)")
    return True
