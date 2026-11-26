"""Automated Order Entry: when a store's "Automated Order" setting is on, a
PM's Order Entry submit (last bill + GRN) is queued instead of processed
immediately.

Flow (owner ruling 2026-11-24):
    1. PM fills last bill / last GRN on Order Entry and submits.
    2. If dbo.StoreOrderAutomation.AutomatedOrderEnabled is off for the store,
       nothing changes here -- service.start_pm_order runs exactly as before.
    3. If it's on, the submit is recorded in dbo.StoreAutoOrderQueue and a
       background worker waits a random delay (MinDelaySeconds..MaxDelaySeconds,
       default 1-7 minutes), polling repository.check_order_checkpoint during
       the wait so the run only starts once the entered bill/GRN are actually
       visible in OrderNMC (same check start_order_process itself performs;
       this is a courtesy early/parallel check, not a replacement for it).
    4. The worker then calls service.start_pm_order for real (trigger="auto"),
       waits for that job, and on success sends the ORDER_GENERATED WhatsApp
       notice if that message type is enabled AND the store is in
       ProductionMode -- otherwise the notice is only logged.

The queue table survives a backend restart (unlike service._jobs): a row left
PENDING/RUNNING after a crash is picked up by the same recovery sweep used for
"was this run already claimed" elsewhere in this module -- see resume_pending().
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import random
import re
import threading
import time

from modules.legacy_order import database, repository

logger = logging.getLogger(__name__)

_SQL_PATH = os.path.join(os.path.dirname(__file__), "sql", "0016_auto_order_entry.sql")
_schema_ready = False
_schema_lock = threading.Lock()

CHECKPOINT_POLL_SECONDS = 20
CHECKPOINT_MAX_WAIT_SECONDS = 600  # on top of the random settle delay

MESSAGE_TYPES = ("ORDER_GENERATED", "STOCK_LIST", "TIME_LIST", "STOCK_READY", "ENTRY_READY")


def _ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with open(_SQL_PATH, encoding="utf-8") as fh:
            script = fh.read()
        with database.get_central_connection() as conn:
            cur = conn.cursor()
            for batch in [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.MULTILINE) if b.strip()]:
                cur.execute(batch)
            conn.commit()
        _schema_ready = True


# ---- store automation settings ------------------------------------------------

def get_automation(store_name):
    _ensure_schema()
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT AutomatedOrderEnabled, ProductionMode, MinDelaySeconds, MaxDelaySeconds, "
            "UpdatedAt, UpdatedBy FROM dbo.StoreOrderAutomation WHERE StoreName = ?",
            store_name,
        ).fetchone()
    if not row:
        return {"store_name": store_name, "automated_order_enabled": False, "production_mode": False,
                "min_delay_seconds": 60, "max_delay_seconds": 420, "updated_at": None, "updated_by": None}
    return {
        "store_name": store_name,
        "automated_order_enabled": bool(row.AutomatedOrderEnabled),
        "production_mode": bool(row.ProductionMode),
        "min_delay_seconds": int(row.MinDelaySeconds or 60),
        "max_delay_seconds": int(row.MaxDelaySeconds or 420),
        "updated_at": row.UpdatedAt,
        "updated_by": row.UpdatedBy,
    }


def set_automation(store_name, automated_order_enabled, production_mode,
                    min_delay_seconds=60, max_delay_seconds=420, actor=None):
    _ensure_schema()
    min_delay_seconds = max(0, int(min_delay_seconds or 0))
    max_delay_seconds = max(min_delay_seconds, int(max_delay_seconds or min_delay_seconds))
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        updated = cur.execute(
            "UPDATE dbo.StoreOrderAutomation SET AutomatedOrderEnabled = ?, ProductionMode = ?, "
            "MinDelaySeconds = ?, MaxDelaySeconds = ?, UpdatedAt = GETDATE(), UpdatedBy = ? WHERE StoreName = ?",
            1 if automated_order_enabled else 0, 1 if production_mode else 0,
            min_delay_seconds, max_delay_seconds, actor, store_name,
        ).rowcount
        if not updated:
            cur.execute(
                "INSERT INTO dbo.StoreOrderAutomation (StoreName, AutomatedOrderEnabled, ProductionMode, "
                "MinDelaySeconds, MaxDelaySeconds, UpdatedBy) VALUES (?, ?, ?, ?, ?, ?)",
                store_name, 1 if automated_order_enabled else 0, 1 if production_mode else 0,
                min_delay_seconds, max_delay_seconds, actor,
            )
        conn.commit()
    return get_automation(store_name)


# ---- message-type settings ----------------------------------------------------

def _row_to_message_setting(row):
    try:
        targets = json.loads(row.TargetsJson) if row.TargetsJson else []
    except ValueError:
        targets = []
    return {
        "store_name": row.StoreName, "message_type": row.MessageType, "enabled": bool(row.Enabled),
        "targets": targets, "updated_at": row.UpdatedAt, "updated_by": row.UpdatedBy,
    }


def list_message_settings(store_name):
    _ensure_schema()
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(
            "SELECT StoreName, MessageType, Enabled, TargetsJson, UpdatedAt, UpdatedBy "
            "FROM dbo.StoreMessageSettings WHERE StoreName = ?",
            store_name,
        ).fetchall()
    by_type = {r.MessageType: _row_to_message_setting(r) for r in rows}
    return [by_type.get(mt, {"store_name": store_name, "message_type": mt, "enabled": False,
                              "targets": [], "updated_at": None, "updated_by": None})
            for mt in MESSAGE_TYPES]


def get_message_setting(store_name, message_type):
    _ensure_schema()
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT StoreName, MessageType, Enabled, TargetsJson, UpdatedAt, UpdatedBy "
            "FROM dbo.StoreMessageSettings WHERE StoreName = ? AND MessageType = ?",
            store_name, message_type,
        ).fetchone()
    return _row_to_message_setting(row) if row else {
        "store_name": store_name, "message_type": message_type, "enabled": False,
        "targets": [], "updated_at": None, "updated_by": None,
    }


def save_message_setting(store_name, message_type, enabled, targets, actor=None):
    _ensure_schema()
    message_type = str(message_type or "").strip().upper()
    if message_type not in MESSAGE_TYPES:
        raise ValueError(f"Message type must be one of {', '.join(MESSAGE_TYPES)}.")
    from modules.legacy_order.supplier_whatsapp import normalize_targets
    targets = normalize_targets(targets)
    targets_json = json.dumps(targets, ensure_ascii=False) if targets else None
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        updated = cur.execute(
            "UPDATE dbo.StoreMessageSettings SET Enabled = ?, TargetsJson = ?, UpdatedAt = GETDATE(), "
            "UpdatedBy = ? WHERE StoreName = ? AND MessageType = ?",
            1 if enabled else 0, targets_json, actor, store_name, message_type,
        ).rowcount
        if not updated:
            cur.execute(
                "INSERT INTO dbo.StoreMessageSettings (StoreName, MessageType, Enabled, TargetsJson, UpdatedBy) "
                "VALUES (?, ?, ?, ?, ?)",
                store_name, message_type, 1 if enabled else 0, targets_json, actor,
            )
        conn.commit()
    return get_message_setting(store_name, message_type)


# ---- queue ---------------------------------------------------------------------

def _insert_queue_row(store_name, last_bill, last_grn, order_type, confirmed, run_at, actor):
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.StoreAutoOrderQueue (StoreName, LastBill, LastGrn, OrderType, Confirmed, "
            "Status, RunAt, QueuedBy) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)",
            store_name, last_bill, last_grn, order_type, 1 if confirmed else 0, run_at, actor,
        )
        new_id = cur.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
        conn.commit()
        return int(new_id)


def _update_queue_row(queue_id, **fields):
    sets, values = [], []
    for col, val in fields.items():
        sets.append(f"{col} = ?")
        values.append(val)
    with database.get_central_connection() as conn:
        conn.cursor().execute(
            f"UPDATE dbo.StoreAutoOrderQueue SET {', '.join(sets)} WHERE Id = ?",
            *values, queue_id,
        )
        conn.commit()


def get_queue_row(queue_id):
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT Id, StoreName, LastBill, LastGrn, OrderType, Confirmed, Status, QueuedAt, RunAt, "
            "StartedAt, FinishedAt, JobId, Error FROM dbo.StoreAutoOrderQueue WHERE Id = ?",
            queue_id,
        ).fetchone()
    return _row_to_queue(row) if row else None


def latest_queue_row(store_name):
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT TOP 1 Id, StoreName, LastBill, LastGrn, OrderType, Confirmed, Status, QueuedAt, RunAt, "
            "StartedAt, FinishedAt, JobId, Error FROM dbo.StoreAutoOrderQueue "
            "WHERE StoreName = ? ORDER BY Id DESC",
            store_name,
        ).fetchone()
    return _row_to_queue(row) if row else None


def _row_to_queue(row):
    return {
        "queue_id": row.Id, "store_name": row.StoreName, "last_bill": row.LastBill, "last_grn": row.LastGrn,
        "order_type": row.OrderType, "confirmed": bool(row.Confirmed), "status": row.Status,
        "queued_at": row.QueuedAt, "run_at": row.RunAt, "started_at": row.StartedAt,
        "finished_at": row.FinishedAt, "job_id": row.JobId, "error": row.Error,
    }


def _notify_order_generated(store_name, header):
    """Best-effort HO WhatsApp notice; never raises into the worker thread."""
    try:
        setting = get_message_setting(store_name, "ORDER_GENERATED")
        if not setting["enabled"] or not setting["targets"]:
            return
        automation = get_automation(store_name)
        order_no = (header or {}).get("order_no")
        order_id = (header or {}).get("order_id")
        text = f"Order generated for {store_name} - Order #{order_no or '?'} ({order_id or ''})."
        if not automation["production_mode"]:
            logger.info("[AUTO_ORDER_ENTRY] test mode, not sending: %s -> %s", store_name, text)
            return
        from modules.legacy_order import database as _db
        from modules.whatsapp import service as whatsapp_service
        profile_id = os.getenv("WHATSAPP_HO_PROFILE_ID", "")
        if not profile_id:
            logger.warning("[AUTO_ORDER_ENTRY] WHATSAPP_HO_PROFILE_ID not set; cannot send %s", store_name)
            return
        for target in setting["targets"]:
            try:
                whatsapp_service.send_message(profile_id, target["name"], text)
            except Exception:
                logger.exception("[AUTO_ORDER_ENTRY] WhatsApp send failed for %s -> %s", store_name, target)
    except Exception:
        logger.exception("[AUTO_ORDER_ENTRY] notify failed for %s", store_name)


def _wait_for_checkpoint(store_name, last_bill, last_grn, deadline):
    """Poll check_order_checkpoint until ok or the deadline passes. Never
    raises -- a timed-out checkpoint still lets start_pm_order run (which
    re-verifies for real); this is just avoiding an obviously-too-early start."""
    while time.monotonic() < deadline:
        try:
            check = repository.check_order_checkpoint(store_name, last_bill, last_grn)
            if check["ok"]:
                return True
        except Exception:
            logger.exception("[AUTO_ORDER_ENTRY] checkpoint check failed for %s", store_name)
        time.sleep(CHECKPOINT_POLL_SECONDS)
    return False


def _worker(queue_id, store_name, last_bill, last_grn, order_type, confirmed, delay_seconds):
    from modules.legacy_order import service

    time.sleep(delay_seconds)
    deadline = time.monotonic() + CHECKPOINT_MAX_WAIT_SECONDS
    _wait_for_checkpoint(store_name, last_bill, last_grn, deadline)

    _update_queue_row(queue_id, Status="RUNNING", StartedAt=datetime.datetime.now())
    try:
        job_id = service.start_pm_order(store_name, last_bill, last_grn, order_type, confirmed, trigger="auto")
        _update_queue_row(queue_id, JobId=job_id)
        deadline = time.monotonic() + 90 * 60
        job = None
        while time.monotonic() < deadline:
            job = service.get_job(job_id)
            if not job or job["status"] != "running":
                break
            time.sleep(5)
        if job and job["status"] == "completed":
            _update_queue_row(queue_id, Status="DONE", FinishedAt=datetime.datetime.now())
            _notify_order_generated(store_name, (job.get("result") or {}).get("header"))
        else:
            error = (job or {}).get("error") or "Order process did not finish."
            _update_queue_row(queue_id, Status="FAILED", FinishedAt=datetime.datetime.now(), Error=str(error))
    except Exception as exc:
        logger.exception("[AUTO_ORDER_ENTRY] auto process failed for %s", store_name)
        _update_queue_row(queue_id, Status="FAILED", FinishedAt=datetime.datetime.now(), Error=str(exc))


def validate_pm_order_upfront(store_name, order_type, confirmed):
    """Same PreviousOrderNotFinalized check start_pm_order itself does, run
    BEFORE queueing so the PM sees that failure immediately instead of
    minutes later when the deferred worker calls start_pm_order for real."""
    from modules.legacy_order import service

    if not str(order_type or "REGULAR").upper() in ("REGULAR", "WH"):
        raise ValueError("Order type must be REGULAR or WH.")
    block = repository.previous_day_order_block(store_name)
    if block:
        raise service.PreviousOrderNotFinalized(
            f"Finish order #{block.get('order_no') or block['order_id']} from "
            f"{str(block['order_id'])[6:8]}/{str(block['order_id'])[4:6]} first: "
            f"{block['qty_pending']} quantity checks and {block['unassigned_lines']} supplier "
            "assignments are pending. Review and Finalize it in the Order Workspace."
        )


def queue_auto_order(store_name, last_bill, last_grn, order_type, confirmed, actor=None):
    """Called instead of service.start_pm_order when AutomatedOrderEnabled is
    on. Returns the queue row (not a service job_id -- the caller polls
    latest_queue_row/get_queue_row instead of service.get_job until Status
    leaves PENDING/RUNNING)."""
    _ensure_schema()
    if not str(last_bill or "").strip() or not str(last_grn or "").strip():
        raise ValueError("Enter the store's last bill and last GRN.")
    validate_pm_order_upfront(store_name, order_type, confirmed)
    automation = get_automation(store_name)
    delay_seconds = random.uniform(automation["min_delay_seconds"], automation["max_delay_seconds"])
    run_at = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)
    queue_id = _insert_queue_row(store_name, last_bill, last_grn, order_type, confirmed, run_at, actor)
    threading.Thread(
        target=_worker, args=(queue_id, store_name, last_bill, last_grn, order_type, confirmed, delay_seconds),
        name=f"auto-order-entry-{store_name}", daemon=True,
    ).start()
    return get_queue_row(queue_id)
