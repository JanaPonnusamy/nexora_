"""Morning auto order: ONE Order Process per chosen store per day, started
by the store itself coming online (owner request 2026-11-26, .32 SMS tenant):

  1. from the window's start time (default 07:45, no new start after
     09:00), wait for the store's
     agent heartbeat (NEXORA_PLATFORM.dbo.store_agent_registry) -- a LAN
     store counts as online when its branch SQL answers;
  2. run the store's normal sync-then-order job, which first asks the device
     for a live sync, then checks that a sale bill dated TODAY is in the
     tenant's SaleInformation (proof the sync caught up with the opened
     store) -- no bill yet = no order, retried every `retry_minutes`;
  3. the order itself (the store's saved engine / source / compare mode);
  4. push the tenant's warehouse stock (SHP for SMS, NMW otherwise -- see
     order_process._warehouse_stock_source_for) into the store's
     SupplierStock, after the order so it is the freshest copy.

Stores run in the configured order (SMG, SMA, SMF for SMS): each pass starts
the first store in that list that is due and online, so a store still waiting
for its PC does not hold the next one back. Runs on the configured weekdays
only (default Monday-Saturday, no Sunday).

Auto-repair (morning_repair): from PREPARE_MINUTES before the start time, an
outdated Store Agent is updated to the current release before the store's
first sync; a failed sync restarts the agent (heartbeat live) or updates /
reinstalls it (no heartbeat but the PC's Device Controller is up), then the
order is retried a minute later.

Unlike the evening order, this is tenant-aware: every legacy database the HO
serves (the default plus each tenant's own -- dbo.tenants.legacy_db_name or
LEGACY_DB_DATABASE_BY_TENANT) has its own settings row
(dbo.LegacyOrderSchedule, ScheduleKey 'MORNING') and per-store day log
(dbo.LegacyMorningOrderRun). Stores run one at a time across all tenants (an
Order Process is CPU-heavy on a shared HO). A store that already had a manual
Order Process today is marked done and left alone.

Env:
  LEGACY_MORNING_ORDER_DISABLED=1     don't start the loop (temp/test backends)
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import time

from modules.legacy_order import database, morning_repair, repository

logger = logging.getLogger(__name__)

SCHEDULE_KEY = "MORNING"
DEFAULT_RUN_AT = "07:45"
DEFAULT_UNTIL = "09:00"
DEFAULT_RETRY_MINUTES = 10
DEFAULT_DAYS = [0, 1, 2, 3, 4, 5]  # datetime.weekday(): Monday..Saturday
# Agent updates start this long before the first order start time.
PREPARE_MINUTES = 30
# After an auto-repair step that brought the agent back, retry this soon.
REPAIRED_RETRY_MINUTES = 1
MAX_ATTEMPTS = 12
POLL_SECONDS = 30
JOB_POLL_SECONDS = 5
JOB_TIMEOUT_SECONDS = 90 * 60
# A heartbeat this fresh = the store PC and its agent are up.
HEARTBEAT_FRESH_SECONDS = 120

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
IF COL_LENGTH('dbo.LegacyOrderSchedule', 'Options') IS NULL
    ALTER TABLE dbo.LegacyOrderSchedule ADD Options NVARCHAR(MAX) NULL;
IF OBJECT_ID('dbo.LegacyMorningOrderRun', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyMorningOrderRun (
        StoreName NVARCHAR(50) NOT NULL,
        RunDate DATE NOT NULL,
        Status VARCHAR(16) NOT NULL,
        Attempts INT NOT NULL DEFAULT 0,
        StartedAt DATETIME2(0) NULL,
        LastAttemptAt DATETIME2(0) NULL,
        NextAttemptAt DATETIME2(0) NULL,
        FinishedAt DATETIME2(0) NULL,
        JobId VARCHAR(64) NULL,
        OrderRows INT NULL,
        Message NVARCHAR(1000) NULL,
        CONSTRAINT PK_LegacyMorningOrderRun PRIMARY KEY (StoreName, RunDate)
    );
END;
"""

# Day-log statuses. WAITING = not done yet (store offline / no bill from
# today yet / a failed attempt still inside the window).
WAITING, RUNNING, DONE, MANUAL, FAILED = "WAITING", "RUNNING", "DONE", "MANUAL", "FAILED"

_started = False
_start_lock = threading.Lock()
_run_lock = threading.Lock()  # one store at a time, across every tenant
_schema_ready: set = set()
_current: dict = {}  # what the worker is doing right now (for the UI)


# ---- tenants ----------------------------------------------------------------

def tenants():
    """Every legacy database this HO serves: [{tenant_id, tenant_name,
    database}], the default (tenant_id None) first, one entry per database."""
    out, seen = [], set()

    def add(tenant_id, name):
        token = database.set_active_tenant(tenant_id)
        try:
            db = database.active_database_name()
        finally:
            database.reset_active_tenant(token)
        if db.upper() in seen:
            return
        seen.add(db.upper())
        out.append({"tenant_id": tenant_id, "tenant_name": name, "database": db})

    add(None, None)
    names = {}
    try:
        import pyodbc

        with pyodbc.connect(database.platform_connection_string(), timeout=10) as conn:
            for tid, tname in conn.cursor().execute(
                "SELECT CONVERT(varchar(40), tenant_id), tenant_name FROM dbo.tenants"
            ).fetchall():
                names[(tid or "").upper()] = tname
    except Exception:
        logger.debug("[MORNING_ORDER] tenant names unavailable", exc_info=True)
    for tid in list(names) + list(database._tenant_database_map()):
        add(tid, names.get(tid))
    return out


def _tenant_key(tenant_id):
    return (tenant_id or "").upper() or "DEFAULT"


def _tenant_by_key(key):
    key = str(key or "").upper()
    for t in tenants():
        if _tenant_key(t["tenant_id"]) == key:
            return t
    raise ValueError(f"Unknown tenant '{key}'.")


class _in_tenant:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id

    def __enter__(self):
        self.token = database.set_active_tenant(self.tenant_id)
        return self

    def __exit__(self, *exc):
        database.reset_active_tenant(self.token)


# ---- settings ---------------------------------------------------------------

def _parse_hhmm(value, label):
    try:
        hours, minutes = str(value or "").strip().split(":")
        return datetime.time(int(hours), int(minutes))
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be HH:MM (24-hour), e.g. 07:00.") from None


def _ensure_schema(cur):
    db = database.active_database_name().upper()
    if db not in _schema_ready:
        cur.execute(_SCHEMA_SQL)
        cur.connection.commit()
        _schema_ready.add(db)


def _read_settings():
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_schema(cur)
        row = cur.execute(
            "SELECT Enabled, RunAt, Stores, Options, UpdatedAt, UpdatedBy FROM dbo.LegacyOrderSchedule "
            "WHERE ScheduleKey = ?",
            SCHEDULE_KEY,
        ).fetchone()
    options = {}
    if row and row.Options:
        try:
            options = json.loads(row.Options) or {}
        except ValueError:
            options = {}
    return {
        "enabled": bool(row and row.Enabled),
        "run_at": (str(row.RunAt).strip() if row and row.RunAt else DEFAULT_RUN_AT),
        "until": options.get("until") or DEFAULT_UNTIL,
        "retry_minutes": int(options.get("retry_minutes") or DEFAULT_RETRY_MINUTES),
        "days": _clean_days(options.get("days")),
        "stores": json.loads(row.Stores) if row and row.Stores else None,
        "updated_at": row.UpdatedAt if row else None,
        "updated_by": row.UpdatedBy if row else None,
    }


def _clean_days(days):
    if days is None:
        return list(DEFAULT_DAYS)
    out = set()
    for d in days:
        try:
            if 0 <= int(d) <= 6:
                out.add(int(d))
        except (TypeError, ValueError):
            pass
    return sorted(out)


def _target_stores(configured):
    """Stores in run order. configured None = every active store except the
    warehouse(s) (SHP / NMW: they supply the stores, the morning order is for
    the stores); a list = those stores, in the list's order."""
    from modules.legacy_order import service

    active = [s["store_name"] for s in repository.list_stores(True)]
    if configured is None:
        return [s for s in active if not service.is_warehouse_store(s)]
    by_name = {s.strip().upper(): s for s in active}
    out = []
    for s in configured:
        name = by_name.get(str(s).strip().upper())
        if name and name not in out:
            out.append(name)
    return out


def _day_rows(day):
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_schema(cur)
        rows = cur.execute(
            "SELECT StoreName, Status, Attempts, StartedAt, LastAttemptAt, NextAttemptAt, FinishedAt, "
            "JobId, OrderRows, Message FROM dbo.LegacyMorningOrderRun WHERE RunDate = ?",
            day,
        ).fetchall()
    return {
        r.StoreName.strip().upper(): {
            "store_name": r.StoreName, "status": r.Status, "attempts": r.Attempts,
            "started_at": r.StartedAt, "last_attempt_at": r.LastAttemptAt,
            "next_attempt_at": r.NextAttemptAt, "finished_at": r.FinishedAt,
            "job_id": r.JobId, "order_rows": r.OrderRows, "message": r.Message,
        }
        for r in rows
    }


def _tenant_status(t, now=None):
    now = now or datetime.datetime.now()
    with _in_tenant(t["tenant_id"]):
        settings = _read_settings()
        from modules.legacy_order import service

        available = [s["store_name"] for s in repository.list_stores(True) if not service.is_warehouse_store(s["store_name"])]
        targets = _target_stores(settings["stores"])
        day = _day_rows(now.date())
    stores = []
    for name in targets:
        entry = day.get(name.strip().upper()) or {"store_name": name, "status": WAITING, "attempts": 0}
        if _current.get("store_name") == name and _current.get("tenant") == _tenant_key(t["tenant_id"]):
            entry = {**entry, "status": RUNNING, "step": _current.get("step")}
        stores.append(entry)
    return {
        "tenant_key": _tenant_key(t["tenant_id"]), "tenant_id": t["tenant_id"],
        "tenant_name": t["tenant_name"], "database": t["database"],
        **settings, "available_stores": available, "today": stores,
    }


def get_schedules():
    out = []
    for t in tenants():
        try:
            out.append(_tenant_status(t))
        except Exception as exc:  # one tenant DB down must not hide the others
            out.append({"tenant_key": _tenant_key(t["tenant_id"]), "tenant_id": t["tenant_id"],
                        "tenant_name": t["tenant_name"], "database": t["database"], "error": str(exc)})
    return {"schedules": out, "running": dict(_current) if _current else None}


def set_schedule(tenant_key, enabled, run_at, until, stores, retry_minutes=None, actor=None, days=None):
    t = _tenant_by_key(tenant_key)
    start = _parse_hhmm(run_at, "Start time")
    end = _parse_hhmm(until, "Last start")
    if end <= start:
        raise ValueError("The last start time must be after the start time.")
    retry = int(retry_minutes or DEFAULT_RETRY_MINUTES)
    if not 2 <= retry <= 120:
        raise ValueError("Retry every 2 to 120 minutes.")
    if stores is not None:
        ordered = []  # the list order is the run order
        for s in stores:
            s = str(s).strip()
            if s and s.upper() not in {o.upper() for o in ordered}:
                ordered.append(s)
        stores = ordered
        if enabled and not stores:
            raise ValueError("Pick at least one store for the morning order.")
    days = _clean_days(days)
    if enabled and not days:
        raise ValueError("Pick at least one day for the morning order.")
    options = json.dumps({"until": end.strftime("%H:%M"), "retry_minutes": retry, "days": days})
    stores_json = json.dumps(stores) if stores is not None else None
    with _in_tenant(t["tenant_id"]):
        with database.get_central_connection() as conn:
            cur = conn.cursor()
            _ensure_schema(cur)
            cur.execute(
                "MERGE dbo.LegacyOrderSchedule AS t USING (SELECT ? AS ScheduleKey) AS s "
                "ON t.ScheduleKey = s.ScheduleKey "
                "WHEN MATCHED THEN UPDATE SET Enabled = ?, RunAt = ?, Stores = ?, Options = ?, "
                "  UpdatedAt = SYSUTCDATETIME(), UpdatedBy = ? "
                "WHEN NOT MATCHED THEN INSERT (ScheduleKey, Enabled, RunAt, Stores, Options, UpdatedBy) "
                "  VALUES (?, ?, ?, ?, ?, ?);",
                SCHEDULE_KEY, 1 if enabled else 0, start.strftime("%H:%M"), stores_json, options, actor,
                SCHEDULE_KEY, 1 if enabled else 0, start.strftime("%H:%M"), stores_json, options, actor,
            )
            conn.commit()
    return _tenant_status(t)


def reset_store_today(tenant_key, store_name):
    """'Run again' for one store: clear today's log row so the next tick
    picks it up as soon as it is online (counts toward nothing else)."""
    t = _tenant_by_key(tenant_key)
    with _in_tenant(t["tenant_id"]):
        with database.get_central_connection() as conn:
            cur = conn.cursor()
            _ensure_schema(cur)
            cur.execute(
                "DELETE FROM dbo.LegacyMorningOrderRun WHERE StoreName = ? AND RunDate = ? AND Status <> ?",
                store_name, datetime.date.today(), RUNNING,
            )
            conn.commit()
    return _tenant_status(t)


# ---- the day log ------------------------------------------------------------

def _claim(store_name, now):
    """WAITING/no row -> RUNNING for today, atomically (one backend wins)."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "MERGE dbo.LegacyMorningOrderRun WITH (HOLDLOCK) AS t "
            "USING (SELECT ? AS StoreName, ? AS RunDate) AS s "
            "ON t.StoreName = s.StoreName AND t.RunDate = s.RunDate "
            "WHEN MATCHED AND t.Status = ? AND (t.NextAttemptAt IS NULL OR t.NextAttemptAt <= ?) THEN "
            "  UPDATE SET Status = ?, Attempts = t.Attempts + 1, LastAttemptAt = ?, NextAttemptAt = NULL, "
            "  StartedAt = ISNULL(t.StartedAt, ?), Message = ? "
            "WHEN NOT MATCHED THEN INSERT (StoreName, RunDate, Status, Attempts, StartedAt, LastAttemptAt, Message) "
            "  VALUES (?, ?, ?, 1, ?, ?, ?);",
            store_name, now.date(), WAITING, now, RUNNING, now, now, "Starting…",
            store_name, now.date(), RUNNING, now, now, "Starting…",
        )
        claimed = cur.rowcount == 1
        conn.commit()
    return claimed


def _mark(store_name, day, status, message, *, retry_at=None, job_id=None, rows=None, finished=False):
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "MERGE dbo.LegacyMorningOrderRun AS t USING (SELECT ? AS StoreName, ? AS RunDate) AS s "
            "ON t.StoreName = s.StoreName AND t.RunDate = s.RunDate "
            "WHEN MATCHED THEN UPDATE SET Status = ?, Message = ?, NextAttemptAt = ?, "
            "  JobId = ISNULL(?, t.JobId), OrderRows = ISNULL(?, t.OrderRows), "
            "  FinishedAt = CASE WHEN ? = 1 THEN SYSDATETIME() ELSE t.FinishedAt END "
            "WHEN NOT MATCHED THEN INSERT (StoreName, RunDate, Status, Message, NextAttemptAt, JobId, OrderRows, FinishedAt) "
            "  VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 1 THEN SYSDATETIME() ELSE NULL END);",
            store_name, day, status, (message or "")[:1000], retry_at, job_id, rows, 1 if finished else 0,
            store_name, day, status, (message or "")[:1000], retry_at, job_id, rows, 1 if finished else 0,
        )
        conn.commit()


# ---- the run ----------------------------------------------------------------

def store_online(store_name):
    """(online, detail). Agent-synced stores: a fresh agent heartbeat. LAN
    stores: the branch SQL answers."""
    from modules.legacy_order import device_sync, service

    store = service._resolve_store(store_name)
    if service.is_agent_synced_store(store_name, store):
        store_id = database.platform_store_id(store["store_name"])
        if not store_id:
            return False, "no platform store_id"
        age = device_sync._agent_heartbeat_age_seconds(store_id)
        if age is None:
            return False, "no agent heartbeat yet"
        return age <= HEARTBEAT_FRESH_SECONDS, f"agent heartbeat {age}s ago"
    ok, error = repository.test_branch_connection(store)
    return ok, "branch reachable" if ok else f"branch unreachable: {error}"


def _wait_for_job(job_id):
    from modules.legacy_order import service

    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if not job or job["status"] != "running":
            return job
        _current["step"] = (job or {}).get("message")
        time.sleep(JOB_POLL_SECONDS)
    return service.get_job(job_id)


def _is_sync_failure(job):
    """The job stopped in its sync step (device sync or platform copy)."""
    message = str(job.get("message") or "")
    return message.startswith(("Live device sync did not complete", "Platform sync failed"))


def run_store(store_name, settings, now):
    """Steps 2-4 for one store whose today row this caller just claimed."""
    from modules.legacy_order import order_process, rulebook_order, service

    day = now.date()
    retry_at = now + datetime.timedelta(minutes=settings["retry_minutes"])
    until = datetime.datetime.combine(day, _parse_hhmm(settings["until"], "Last start"))

    def again(message):
        attempts = _day_rows(day).get(store_name.strip().upper(), {}).get("attempts") or 0
        if retry_at > until or attempts >= MAX_ATTEMPTS:
            _mark(store_name, day, FAILED, f"{message} Gave up after {attempts} attempt(s).", finished=True)
        else:
            _mark(store_name, day, WAITING, f"{message} Retrying at {retry_at:%H:%M}.", retry_at=retry_at)

    note = morning_repair.prepare(store_name, progress=lambda m: _current.update(step=m))
    if note:
        _mark(store_name, day, RUNNING, note)

    def repaired_again(message):
        """A sync failure: one auto-repair step, then retry soon if it worked."""
        _current["step"] = "Sync failed -- auto-repair…"
        ok, fix = morning_repair.repair(store_name, "sync failed", progress=lambda m: _current.update(step=m))
        if ok:
            soon = datetime.datetime.now() + datetime.timedelta(minutes=REPAIRED_RETRY_MINUTES)
            if soon <= until:
                _mark(store_name, day, WAITING, f"{message} {fix} Retrying at {soon:%H:%M}.", retry_at=soon)
                return
        again(f"{message} {fix}" if fix else message)

    try:
        job_id = service.start_order_process(
            store_name, mode=rulebook_order.get_order_mode(store_name) or "local",
            confirmed_stale_order=True, trigger="morning", require_today_bill=True,
        )
    except Exception as exc:  # a job already running, unreachable branch ...
        again(f"Not started: {exc}")
        return
    _mark(store_name, day, RUNNING, "Syncing and generating the order…", job_id=job_id)
    job = _wait_for_job(job_id) or {}
    result = job.get("result") or {}
    if job.get("status") != "completed":
        check = result.get("checkpoint") or {}
        failure = job.get("error") or job.get("message") or "The order job did not complete."
        if check and not check.get("ok"):
            again(check.get("message") or "No sale bill from today yet.")
        elif _is_sync_failure(job):
            repaired_again(f"Sync failed: {failure}")
        else:
            again(failure)
        return

    message = f"Order generated ({result.get('rows')} rows)."
    store = service._resolve_store(store_name)
    source = order_process._warehouse_stock_source_for(store)
    if store["store_name"].upper() != source.upper() and store.get("ho_code") and not service.is_warehouse_store(store_name):
        _current["step"] = f"Pushing {source} stock…"
        try:
            inserted, _ = order_process.refresh_warehouse_stock(store, source)
            message += f" {source} stock pushed ({inserted} rows)."
        except Exception as exc:
            logger.exception("[MORNING_ORDER] %s stock push failed for %s", source, store_name)
            message += f" {source} stock push failed: {exc}"
    _mark(store_name, day, DONE, message, rows=result.get("rows"), finished=True)


def _locked(fn):
    """Run fn under the one-at-a-time lock; False if another run holds it."""
    if not _run_lock.acquire(blocking=False):
        return False
    try:
        fn()
        return True
    finally:
        _current.clear()
        _run_lock.release()


def _prepare_due(store_name, now, start):
    """Before the start time: bring the store's agent up to date (once)."""
    notes = []

    def prep():
        _current.update(store_name=store_name, started_at=now.isoformat(timespec="seconds"),
                        step="Checking the Store Agent version…")
        notes.append(morning_repair.prepare(store_name, progress=lambda m: _current.update(step=m)))

    if not _locked(prep):
        return None
    return notes[0] if notes else None


def _repair_offline(store_name, detail, now):
    """No agent heartbeat but the PC's Device Controller is up: one repair
    step. Returns the note, or None when nothing could be done."""
    try:
        device, _, _ = morning_repair._online_device(store_name)
    except Exception:
        logger.debug("[MORNING_ORDER] device lookup failed for %s", store_name, exc_info=True)
        return None
    if not device:
        return None
    fixed = []

    def fix():
        _current.update(store_name=store_name, started_at=now.isoformat(timespec="seconds"),
                        step="No agent heartbeat -- auto-repair…")
        fixed.append(morning_repair.repair(store_name, detail, progress=lambda m: _current.update(step=m)))

    if not _locked(fix) or not fixed:
        return None
    return fixed[0][1]


def tick(now=None):
    """One scheduler pass over every tenant; does at most ONE store's work
    (an agent update, an auto-repair step or the order run) and returns its
    name, else None."""
    from modules.legacy_order import rulebook_order

    now = now or datetime.datetime.now()
    if _run_lock.locked():
        return None
    for t in tenants():
        with _in_tenant(t["tenant_id"]):
            try:
                settings = _read_settings()
            except Exception:
                logger.debug("[MORNING_ORDER] %s settings unreadable", t["database"], exc_info=True)
                continue
            if not settings["enabled"] or now.weekday() not in settings["days"]:
                continue
            start = datetime.datetime.combine(now.date(), _parse_hhmm(settings["run_at"], "Start time"))
            until = datetime.datetime.combine(now.date(), _parse_hhmm(settings["until"], "Last start"))
            if not start - datetime.timedelta(minutes=PREPARE_MINUTES) <= now <= until:
                continue
            tkey = _tenant_key(t["tenant_id"])
            _current_tenant = {"tenant": tkey}
            day = _day_rows(now.date())
            for name in _target_stores(settings["stores"]):
                row = day.get(name.strip().upper())
                if row and row["status"] != WAITING:
                    continue
                if now < start:
                    if morning_repair.prepared_today(name):
                        continue
                    _current.update(_current_tenant)
                    note = _prepare_due(name, now, start)
                    if note:
                        _mark(name, now.date(), WAITING, note)
                        return name
                    continue

                if row and row["next_attempt_at"] and row["next_attempt_at"] > now:
                    continue
                midnight = datetime.datetime.combine(now.date(), datetime.time())
                if rulebook_order.ran_manually_today(name, midnight):
                    _mark(name, now.date(), MANUAL, "Order Process already run manually today.", finished=True)
                    continue
                try:
                    online, detail = store_online(name)
                except Exception as exc:
                    online, detail = False, str(exc)
                if not online:
                    _current.update(_current_tenant)
                    note = _repair_offline(name, detail, now)
                    if note:
                        _mark(name, now.date(), WAITING, f"Store agent not beating ({detail}). {note}")
                        return name
                    if not row or not str(row.get("message") or "").startswith(("Waiting for the store", "Store agent")):
                        _mark(name, now.date(), WAITING, f"Waiting for the store to come online ({detail}).")
                    continue

                def go(_name=name, _detail=detail):
                    if not _claim(_name, now):
                        return
                    _current.update(store_name=_name, tenant=tkey,
                                    started_at=now.isoformat(timespec="seconds"), step="Starting…")
                    logger.info("[MORNING_ORDER] %s (%s) online (%s): starting", _name, t["database"], _detail)
                    try:
                        run_store(_name, settings, now)
                    except Exception as exc:
                        logger.exception("[MORNING_ORDER] %s run failed", _name)
                        _mark(_name, now.date(), WAITING, f"Run failed: {exc}",
                              retry_at=now + datetime.timedelta(minutes=settings["retry_minutes"]))

                if not _locked(go):
                    return None
                return name
    return None


def _loop():
    time.sleep(90)  # let the backend finish starting first
    last_error_logged = 0.0
    while True:
        try:
            tick()
        except Exception:
            if time.monotonic() - last_error_logged > 1800:
                last_error_logged = time.monotonic()
                logger.exception("[MORNING_ORDER] check failed")
        time.sleep(POLL_SECONDS)


def start_background_loop():
    global _started
    if os.getenv("LEGACY_MORNING_ORDER_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return False
    with _start_lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, name="legacy-morning-order", daemon=True).start()
    print("[MORNING_ORDER] scheduler started (settings: Legacy Order > Morning auto order)")
    return True
