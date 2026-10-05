"""Data access for the sync scheduler (SYNC-SCHED-01).

ROOT CAUSE this module fixes: nothing in the codebase ever read
dbo.sync_schedule and turned it into a dbo.sync_execution row. The Schedule
Plan screen could create/enable/suspend schedule rows all day long -- they
were pure metadata with no reader. The only function that ever inserted a
PENDING execution (runtime_repository.create_task, behind
POST /api/sync/tasks/create) was called from exactly one place in the whole
codebase: the manual "Sync Now" / "Sync All" buttons in Live Operations. See
scheduler_service.py for the tick that now reads sync_schedule on a timer and
calls dispatch() below for every due store.

LOCKING: "one active sync per store" is enforced with SQL Server's built-in
distributed lock (sp_getapplock), NOT an in-memory flag. @LockOwner is
'Transaction' -- the lock is held only for the duration of the atomic
check-then-write below and is released automatically at COMMIT/ROLLBACK, so it
can never leak past a crashed process. The *sync itself* being "in progress"
is represented structurally by the sync_execution row's status (PENDING /
RUNNING), which is recovered independently by
SyncAdminRepository._reap_stale_executions (heartbeat + 2h ceiling) -- that is
the lease/heartbeat mechanism the lock-recovery requirement asks for.

This module is called from at most one worker at a time: scheduler_service's
tick loop wraps every call here in its own whole-tick sp_getapplock
(see acquire_tick_lock), so even with multiple backend processes only one
tick is ever "in flight" system-wide.
"""
import datetime as _dt
import socket
import os

from config.database import get_connection

WORKER_ID = "%s:%s" % (socket.gethostname(), os.getpid())

_schema_ready = False


def _audit(cur, execution_id, action_name, message=None):
    cur.execute(
        "INSERT INTO dbo.sync_execution_audit (execution_id, action_name, message) "
        "VALUES (?, ?, ?)",
        (execution_id, action_name, message),
    )


def ensure_schema(cur):
    """Idempotent ALTERs for the columns the scheduler needs on
    dbo.sync_execution. Mirrors the COL_LENGTH-guard pattern already used by
    SyncAdminRepository.ensure_schema for dbo.sync_schedule."""
    global _schema_ready
    if _schema_ready:
        return
    for stmt in (
        "IF COL_LENGTH('dbo.sync_execution','schedule_id') IS NULL "
        "ALTER TABLE dbo.sync_execution ADD schedule_id BIGINT NULL",
        "IF COL_LENGTH('dbo.sync_execution','trigger_type') IS NULL "
        "ALTER TABLE dbo.sync_execution ADD trigger_type VARCHAR(20) NOT NULL "
        "CONSTRAINT DF_sync_execution_trigger_type DEFAULT 'MANUAL'",
        "IF COL_LENGTH('dbo.sync_execution','scheduled_time') IS NULL "
        "ALTER TABLE dbo.sync_execution ADD scheduled_time DATETIME NULL",
        "IF COL_LENGTH('dbo.sync_execution','skip_reason') IS NULL "
        "ALTER TABLE dbo.sync_execution ADD skip_reason VARCHAR(500) NULL",
        # Diagnostic "worker/job id" -- which HO process (host:pid) claimed
        # this execution. Lets TEST 4 (two workers, one store) be proven from
        # the row itself instead of by inference.
        "IF COL_LENGTH('dbo.sync_execution','claimed_by') IS NULL "
        "ALTER TABLE dbo.sync_execution ADD claimed_by VARCHAR(200) NULL",
        # Helps the (store_id, schedule_id, scheduled_time) lookup that
        # dispatch() runs on every tick for every due store.
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name = 'IX_sync_execution_store_schedule_slot') "
        "CREATE INDEX IX_sync_execution_store_schedule_slot "
        "ON dbo.sync_execution (store_id, schedule_id, scheduled_time)",
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes "
        "WHERE name = 'IX_sync_execution_store_status') "
        "CREATE INDEX IX_sync_execution_store_status "
        "ON dbo.sync_execution (store_id, execution_status)",
    ):
        cur.execute(stmt)
    _schema_ready = True


def acquire_tick_lock(conn, timeout_ms=1000):
    """Whole-tick mutex so only one backend worker process runs a scheduler
    tick at a time (Session-scoped: released when `conn` is closed, even on a
    crash). Returns True if this call got the lock."""
    cur = conn.cursor()
    cur.execute(
        "DECLARE @r INT; "
        "EXEC @r = sp_getapplock @Resource='nexora_scheduler_tick', "
        "@LockMode='Exclusive', @LockOwner='Session', @LockTimeout=?; "
        "SELECT @r;",
        (timeout_ms,),
    )
    result = cur.fetchone()[0]
    return result is not None and result >= 0


def release_tick_lock(conn):
    try:
        cur = conn.cursor()
        cur.execute("EXEC sp_releaseapplock @Resource='nexora_scheduler_tick', @LockOwner='Session';")
        conn.commit()
    except Exception:
        pass


def get_enabled_interval_schedules(cur):
    """All INTERVAL-type schedules eligible to fire right now (enabled, not
    currently suspended). Due-ness itself is computed live from
    interval_minutes + wall clock in scheduler_service -- see
    modules/sync/scheduler_time.py for why next_run_at is never persisted."""
    cur.execute(
        """
        SELECT schedule_id, tenant_id, store_id, schedule_name, interval_minutes, sync_mode
        FROM dbo.sync_schedule
        WHERE is_enabled = 1
          AND schedule_type = 'INTERVAL'
          AND interval_minutes IS NOT NULL
          AND interval_minutes > 0
          AND (suspended_until IS NULL OR suspended_until <= GETDATE())
        ORDER BY schedule_id
        """
    )
    cols = ["schedule_id", "tenant_id", "store_id", "schedule_name", "interval_minutes", "sync_mode"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def resolve_stores(cur, tenant_id, store_id):
    """A schedule's store_id NULL means "every active store in the tenant"."""
    if store_id:
        cur.execute(
            "SELECT store_id, store_code, store_name, tenant_id FROM dbo.stores "
            "WHERE store_id = ? AND is_active = 1",
            (store_id,),
        )
    else:
        cur.execute(
            "SELECT store_id, store_code, store_name, tenant_id FROM dbo.stores "
            "WHERE tenant_id = ? AND is_active = 1 ORDER BY store_code",
            (tenant_id,),
        )
    cols = ["store_id", "store_code", "store_name", "tenant_id"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def count_active_syncs(cur):
    """Global concurrency budget input: how many stores are RUNNING (real
    load right now) or freshly PENDING (claimed in the last 5 minutes --
    about to start, or its agent just hasn't polled yet) right now.

    A PENDING row does zero work by itself -- no DB read, no chunk upload --
    until an online agent picks it up, so it is not "real load" and must stop
    counting once it is clearly stale. Confirmed against live data: two test
    stores with no live agent each claim one PENDING row per cycle that never
    starts; without this 5-minute cutoff those two permanently-inert rows
    occupy the entire NEXORA_SYNC_MAX_CONCURRENT budget forever and every
    other real store gets stuck at QUEUED. The per-store exclusivity lock in
    dispatch()/claim_manual() is unaffected -- an old PENDING row still blocks
    a second execution for *that same store* (still checked as 'active_row'
    there); this only stops it from also blocking every *other* store's
    schedule."""
    cur.execute(
        "SELECT COUNT(*) FROM dbo.sync_execution "
        "WHERE execution_status = 'RUNNING' "
        "OR (execution_status = 'PENDING' AND started_at >= DATEADD(MINUTE, -5, GETDATE()))"
    )
    return cur.fetchone()[0]


def mark_schedule_fired(cur, schedule_id):
    cur.execute(
        "UPDATE dbo.sync_schedule SET last_run_at = GETDATE() WHERE schedule_id = ?",
        (schedule_id,),
    )


def ensure_default_schedules(cur):
    """SYNC-SCHED-01 required default: every active tenant with no INTERVAL
    schedule gets one enabled, all-stores, every-30-minutes schedule.

    Gated on "no INTERVAL schedule" rather than "no schedule at all" on
    purpose: real tenants in this system already have legacy per-store DAILY
    schedules from the old seed_default_schedules button (confirmed against
    the live DB -- e.g. "NMA Morning Sync"), and those were never wired to
    anything before this fix, so leaving them as the only schedule would mean
    the mandatory 30-minute cadence silently never applies to an existing
    tenant. Pre-existing DAILY/ONCE rows are left completely untouched -- this
    only ever adds the interval schedule alongside them."""
    cur.execute("SELECT tenant_id, tenant_name FROM dbo.tenants WHERE is_active = 1")
    tenants = cur.fetchall()
    created = 0
    for tenant_id, tenant_name in tenants:
        cur.execute(
            "SELECT COUNT(*) FROM dbo.sync_schedule WHERE tenant_id = ? AND schedule_type = 'INTERVAL'",
            (tenant_id,),
        )
        if cur.fetchone()[0] > 0:
            continue
        cur.execute(
            """
            INSERT INTO dbo.sync_schedule
                (tenant_id, store_id, schedule_name, schedule_type, start_time,
                 interval_minutes, sync_mode, is_enabled, created_at, updated_at)
            VALUES (?, NULL, ?, 'INTERVAL', ?, 30, 'FULL', 1, GETDATE(), GETDATE())
            """,
            # start_time is NOT NULL in the live schema and unused by INTERVAL
            # schedules -- same 2000-01-01 placeholder anchor validate_schedule
            # uses for API-created INTERVAL rows (services/sync_admin_service.py).
            (tenant_id, "Every 30 Minutes", _dt.datetime(2000, 1, 1)),
        )
        created += 1
    return created


def get_slot_execution(cur, store_id, schedule_id, scheduled_time):
    cur.execute(
        "SELECT execution_id, execution_status FROM dbo.sync_execution "
        "WHERE store_id = ? AND schedule_id = ? AND scheduled_time = ?",
        (store_id, schedule_id, scheduled_time),
    )
    return cur.fetchone()


def dispatch(schedule, store, scheduled_time, has_slot):
    """Atomically claim, upgrade, skip, or queue one (store, schedule, slot).

    This is the single choke point every path that can start a store's sync
    -- the scheduler tick AND (via runtime_repository.create_task) the manual
    "Sync Now" button -- goes through, so "one active sync per store" holds
    regardless of trigger type.

    Returns dict(outcome=..., execution_id=str|None). Outcomes:
      CLAIMED                 new/queued execution is now PENDING; the
                               store's agent will pick it up on its next poll
      QUEUED                  due, but no concurrency slot free right now
      STILL_QUEUED            already QUEUED for this slot, still waiting
      SKIPPED_ALREADY_RUNNING first time seeing this slot, but the store
                               already has another PENDING/RUNNING execution
      ALREADY_HANDLED         this slot already resolved (no-op)
      LOCK_CONTENDED          could not get the per-store lock this attempt;
                               caller should retry on the next tick
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        ensure_schema(cur)

        lock_name = "nexora_sync_store:" + str(store["store_id"])
        cur.execute(
            "DECLARE @r INT; "
            "EXEC @r = sp_getapplock @Resource=?, @LockMode='Exclusive', "
            "@LockOwner='Transaction', @LockTimeout=3000; SELECT @r;",
            (lock_name,),
        )
        acquired = cur.fetchone()[0]
        if acquired is None or acquired < 0:
            conn.rollback()
            return {"outcome": "LOCK_CONTENDED", "execution_id": None}

        slot_row = get_slot_execution(cur, store["store_id"], schedule["schedule_id"], scheduled_time)

        cur.execute(
            "SELECT TOP 1 execution_id FROM dbo.sync_execution "
            "WHERE store_id = ? AND execution_status IN ('PENDING','RUNNING')",
            (store["store_id"],),
        )
        active_row = cur.fetchone()

        if slot_row is not None:
            slot_execution_id, slot_status = slot_row
            if slot_status != "QUEUED":
                conn.commit()
                return {"outcome": "ALREADY_HANDLED", "execution_id": str(slot_execution_id)}
            if active_row is not None or not has_slot:
                conn.commit()
                return {"outcome": "STILL_QUEUED", "execution_id": str(slot_execution_id)}
            cur.execute(
                "UPDATE dbo.sync_execution SET execution_status = 'PENDING', "
                "claimed_by = ?, started_at = GETDATE() WHERE execution_id = ?",
                (WORKER_ID, slot_execution_id),
            )
            _audit(cur, slot_execution_id, "PENDING", "Scheduler promoted queued execution to PENDING")
            mark_schedule_fired(cur, schedule["schedule_id"])
            conn.commit()
            return {"outcome": "CLAIMED", "execution_id": str(slot_execution_id)}

        # First time seeing (store, schedule, scheduled_time).
        if active_row is not None:
            cur.execute(
                """
                INSERT INTO dbo.sync_execution
                    (tenant_id, store_id, schedule_id, execution_type, sync_mode,
                     execution_status, trigger_type, scheduled_time, total_tables,
                     completed_tables, failed_tables, skip_reason, started_at, completed_at)
                OUTPUT INSERTED.execution_id
                VALUES (?, ?, ?, 'FULL', ?, 'SKIPPED', 'SCHEDULED', ?, 0, 0, 0, ?, GETDATE(), GETDATE())
                """,
                (store["tenant_id"], store["store_id"], schedule["schedule_id"], schedule["sync_mode"],
                 scheduled_time, "Skipped - store already syncing (execution %s)" % active_row[0]),
            )
            new_id = cur.fetchone()[0]
            _audit(cur, new_id, "SKIPPED", "Store already syncing: execution %s" % active_row[0])
            conn.commit()
            return {"outcome": "SKIPPED_ALREADY_RUNNING", "execution_id": str(new_id),
                    "existing_execution_id": str(active_row[0])}

        status = "PENDING" if has_slot else "QUEUED"
        cur.execute(
            """
            INSERT INTO dbo.sync_execution
                (tenant_id, store_id, schedule_id, execution_type, sync_mode,
                 execution_status, trigger_type, scheduled_time, total_tables,
                 completed_tables, failed_tables, claimed_by, started_at)
            OUTPUT INSERTED.execution_id
            VALUES (?, ?, ?, 'FULL', ?, ?, 'SCHEDULED', ?, 0, 0, 0, ?, GETDATE())
            """,
            (store["tenant_id"], store["store_id"], schedule["schedule_id"], schedule["sync_mode"],
             status, scheduled_time, WORKER_ID if status == "PENDING" else None),
        )
        new_id = cur.fetchone()[0]
        _audit(cur, new_id, status,
               "Scheduled execution created" if status == "PENDING"
               else "Queued - waiting for a concurrency slot")
        if status == "PENDING":
            mark_schedule_fired(cur, schedule["schedule_id"])
        conn.commit()
        return {"outcome": "CLAIMED" if status == "PENDING" else "QUEUED", "execution_id": str(new_id)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def claim_manual(tenant_id, store_id, execution_type, sync_mode, total_tables):
    """Manual 'Sync Now' path (POST /api/sync/tasks/create). Uses the exact
    same per-store sp_getapplock as the scheduler so a user clicking
    "Sync All" while a store is mid-sync joins/observes the existing
    execution instead of queuing a second one behind it.

    Returns dict(execution_id=str, status=str, created=bool).
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        ensure_schema(cur)

        lock_name = "nexora_sync_store:" + str(store_id)
        cur.execute(
            "DECLARE @r INT; "
            "EXEC @r = sp_getapplock @Resource=?, @LockMode='Exclusive', "
            "@LockOwner='Transaction', @LockTimeout=5000; SELECT @r;",
            (lock_name,),
        )
        acquired = cur.fetchone()[0]
        if acquired is None or acquired < 0:
            conn.rollback()
            raise TimeoutError("Could not acquire sync lock for store %s" % store_id)

        cur.execute(
            "SELECT TOP 1 execution_id, execution_status FROM dbo.sync_execution "
            "WHERE store_id = ? AND execution_status IN ('PENDING','RUNNING') "
            "ORDER BY started_at DESC",
            (store_id,),
        )
        active_row = cur.fetchone()
        if active_row is not None:
            conn.commit()
            return {"execution_id": str(active_row[0]), "status": active_row[1], "created": False}

        cur.execute(
            """
            INSERT INTO dbo.sync_execution
                (tenant_id, store_id, execution_type, sync_mode, execution_status,
                 trigger_type, total_tables, claimed_by, started_at, initiated_by, created_by)
            OUTPUT INSERTED.execution_id
            VALUES (?, ?, ?, ?, 'PENDING', 'MANUAL', ?, ?, GETDATE(), NULL, NULL)
            """,
            (tenant_id, store_id, execution_type, sync_mode, total_tables, WORKER_ID),
        )
        new_id = cur.fetchone()[0]
        _audit(cur, new_id, "CREATED", "Task created (manual)")
        conn.commit()
        return {"execution_id": str(new_id), "status": "PENDING", "created": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
