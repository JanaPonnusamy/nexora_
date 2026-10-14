"""Trigger-and-wait for a live NMV device sync before the platform copy.

Agent-synced stores (NMV) have no branch HO can pull from; the Order Process
previously just copied whatever was already sitting in NEXORA_PLATFORM.sync.*
(the device's last upload, however old). This module makes it ask the device
to sync NOW -- the same ``dbo.sync_execution`` task the Sync Live grid's
"Sync" button queues -- and blocks until the device agent reports COMPLETED
(or the timeout trips), so the order is generated from fresh data instead of
a stale snapshot. LAN stores (NMA/NMW/NMC/NMG/NMS) never call this; they pull
the branch directly in the same job, which is itself always fresh.
"""
import time

from config.database import get_connection as platform_connection
from modules.sync import scheduler_repository

POLL_INTERVAL_SECONDS = 2
DEFAULT_TIMEOUT_SECONDS = 300


class DeviceSyncTimeout(TimeoutError):
    """The device did not reach COMPLETED within the timeout."""


class DeviceSyncFailed(RuntimeError):
    """The device reported FAILED for the sync task."""


def _tenant_id(store_id):
    conn = platform_connection()
    try:
        row = conn.cursor().execute(
            "SELECT tenant_id FROM dbo.stores WHERE store_id = ?", store_id
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise ValueError(f"Store '{store_id}' has no tenant_id in NEXORA_PLATFORM.dbo.stores.")
    return str(row[0])


def _execution_status(execution_id):
    conn = platform_connection()
    try:
        row = conn.cursor().execute(
            "SELECT execution_status FROM dbo.sync_execution WHERE execution_id = ?",
            execution_id,
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def trigger_and_wait(store_id, store_code, on_progress=None,
                      timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    """Queue a FULL device sync for ``store_id`` and block until it completes.

    Mirrors Live Operations' "Sync" button (``syncService.createTask`` ->
    POST /api/sync/tasks/create), reusing the same atomic per-store claim so
    this never double-queues against a sync the device is already mid-run on
    -- it joins the existing execution instead.

    Raises DeviceSyncTimeout if the device never reaches a terminal status in
    time, or DeviceSyncFailed if it reports FAILED.
    """
    def report(message):
        if on_progress:
            on_progress(message)

    tenant_id = _tenant_id(store_id)
    report(f"Requesting live sync from {store_code}'s device...")
    claim = scheduler_repository.claim_manual(
        tenant_id, store_id, "FULL", "FULL", total_tables=0
    )
    execution_id = claim["execution_id"]

    deadline = time.monotonic() + timeout_seconds
    last_status = claim["status"]
    report(f"Waiting for {store_code}'s device to sync (status: {last_status})...")

    while time.monotonic() < deadline:
        status = _execution_status(execution_id)
        if status != last_status:
            report(f"{store_code} device sync: {status}")
            last_status = status
        if status == "COMPLETED":
            return execution_id
        if status == "FAILED":
            raise DeviceSyncFailed(
                f"{store_code}'s device reported the sync as FAILED "
                f"(execution_id={execution_id})."
            )
        if status is None:
            raise DeviceSyncFailed(
                f"Sync execution {execution_id} for {store_code} disappeared "
                "before completing."
            )
        time.sleep(POLL_INTERVAL_SECONDS)

    raise DeviceSyncTimeout(
        f"{store_code}'s device did not complete the live sync within "
        f"{timeout_seconds}s (last status: {last_status}, "
        f"execution_id={execution_id}). The device agent may be offline."
    )
