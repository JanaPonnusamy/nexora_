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

    conn = get_connection()
    try:
        repo.store_last_grn(conn, tenant_id, refresh_id, str(last_grn_number).strip())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    _trigger_store_sync(tenant_id, refresh.get("store_id"), last_grn_number)

    summary = reconcile(tenant_id, refresh_id, refresh.get("store_id"), last_grn_number)
    logger.info("GRN submitted tenant=%s refresh=%s grn=%s matched=%s by=%s",
                tenant_id, refresh_id, last_grn_number,
                summary.get("assignments_matched"), submitted_by)
    return {
        "refresh_id": str(refresh_id),
        "last_grn_number": str(last_grn_number).strip(),
        **summary,
    }


def reconcile(tenant_id, refresh_id, store_id=None, last_grn=None):
    """Match synced receipts to assignments and roll up to order items."""
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

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "assignments_matched": matched,
        "items_completed": completed,
        "items_partial": partial,
        "items_pending": pending,
    }
