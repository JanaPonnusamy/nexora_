"""GRN completion + assignment reconciliation service (Sprint 3, Modules 1-2).

submit_grn: validate the Last GRN Number -> store it -> trigger Store Sync
(integration seam) -> reconcile automatically. Reconciliation matches synced
receipts to live assignments (product + supplier), writes received/remaining/
GRN/bill per assignment, and rolls the receipts up to each order item
(completed / partial / pending) — no user intervention. Rules are Python;
this layer orchestrates + persists in one transaction.
"""

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import reconciliation_repository as repo
from modules.procurement import reconciliation_rules as rules

import logging

logger = logging.getLogger("procurement.grn")


def _trigger_store_sync(tenant_id, store_id, last_grn):
    """Integration seam: kick off Store Agent sync and await completion.

    Sync is platform infrastructure (invoked, not exposed). Wire the real sync
    orchestration here; today it is a no-op so reconciliation proceeds against
    whatever is already synced.
    """
    return True


def submit_grn(tenant_id, refresh_id, last_grn_number, submitted_by):
    if not last_grn_number or not str(last_grn_number).strip():
        raise HTTPException(status_code=400, detail="last_grn_number is required")

    refresh = repo.get_refresh(tenant_id, refresh_id)
    if not refresh:
        raise HTTPException(status_code=404, detail="Refresh not found")

    # Single transaction for the whole GRN-submit workflow: storing the Last
    # GRN Number and reconciling against it must commit or roll back
    # together. Previously these were two separate connections/commits
    # (Transaction A: store_last_grn; Transaction B: reconcile's own
    # get_connection()), so a reconcile failure left last_grn_number durably
    # committed with zero reconciliation applied — the exact gap this fixes.
    # reconcile() still defaults to opening its own connection when called
    # without one (see its docstring) — that path is unchanged and is what
    # close_cycle continues to use, one isolated transaction per refresh.
    conn = get_connection()
    try:
        repo.store_last_grn(conn, tenant_id, refresh_id, str(last_grn_number).strip())
        summary = reconcile(tenant_id, refresh_id, refresh.get("store_id"), last_grn_number, conn=conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    _trigger_store_sync(tenant_id, refresh.get("store_id"), last_grn_number)

    logger.info("GRN submitted tenant=%s refresh=%s grn=%s matched=%s by=%s",
                tenant_id, refresh_id, last_grn_number,
                summary.get("assignments_matched"), submitted_by)
    return {
        "refresh_id": str(refresh_id),
        "last_grn_number": str(last_grn_number).strip(),
        **summary,
    }


def reconcile(tenant_id, refresh_id, store_id=None, last_grn=None, conn=None):
    """Match synced receipts to assignments and roll up to order items.

    When `conn` is given, runs on the caller's own transaction — the caller
    owns commit/rollback/close (this is how submit_grn shares its GRN-update
    transaction with reconciliation). When `conn` is None (the default —
    close_cycle's own usage, one call per refresh, each independently
    isolated so one refresh's reconciliation failure doesn't block the
    others), opens, commits/rolls back, and closes its own connection exactly
    as before — no change to that call path's transaction scope.
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        if store_id is None:
            refresh = repo.get_refresh(tenant_id, refresh_id)
            store_id = refresh.get("store_id") if refresh else None

        receipts = repo.read_purchase_receipts(conn, tenant_id, store_id, last_grn)
        assignments = repo.exported_assignments(conn, tenant_id, refresh_id)

        matched = 0
        for a in assignments:
            received, grn_no, bill_no = rules.match_receipts(a, receipts)
            if received <= 0:
                continue
            remaining, status = rules.assignment_state(a["assigned_qty"], received)
            repo.apply_receipt(
                conn, tenant_id, a["assignment_id"],
                received, remaining, status, grn_no, bill_no,
            )
            matched += 1

        completed = partial = pending = 0
        for item in repo.order_items_for_refresh(conn, tenant_id, refresh_id):
            total_received = repo.item_received_total(conn, tenant_id, item["order_item_id"])
            remaining, istatus = rules.item_receipt_state(item["final_qty"], total_received)
            repo.set_item_receipts(
                conn, tenant_id, item["order_item_id"],
                total_received, remaining, istatus,
            )
            if istatus == rules.ITEM_COMPLETED:
                completed += 1
            elif istatus == rules.ITEM_PARTIAL:
                partial += 1
            else:
                pending += 1

        if owns_conn:
            conn.commit()
    except Exception:
        if owns_conn:
            conn.rollback()
        raise
    finally:
        if owns_conn:
            conn.close()

    return {
        "assignments_matched": matched,
        "items_completed": completed,
        "items_partial": partial,
        "items_pending": pending,
    }
