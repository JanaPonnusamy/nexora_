"""Pending Management service (Sprint 3, Module 3).

Pending = remaining_qty > 0 (no separate table). Supports review, quantity
adjustment, skip, carry forward, finalize and manual procurement additions.
Validation in Python.
"""

import logging
from io import BytesIO

from fastapi import HTTPException

from modules.procurement import pending_repository as repo

logger = logging.getLogger("procurement.pending")

_BULK_STATUS = {"carry": "carried", "skip": "skipped", "finalize": "finalized"}


def _require(tenant_id, order_item_id):
    item = repo.get_item(tenant_id, order_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pending item not found")
    return item


def list_pending(tenant_id, refresh_id, page, page_size):
    items, total = repo.list_pending(tenant_id, refresh_id, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def adjust(tenant_id, order_item_id, remaining_qty, reviewed_by):
    if remaining_qty is None or remaining_qty < 0:
        raise HTTPException(status_code=400, detail="remaining_qty cannot be negative")
    _require(tenant_id, order_item_id)
    repo.adjust_pending(tenant_id, order_item_id, remaining_qty, reviewed_by)
    return _require(tenant_id, order_item_id)


def skip(tenant_id, order_item_id, reviewed_by):
    _require(tenant_id, order_item_id)
    repo.set_pending_status(tenant_id, order_item_id, "skipped", reviewed_by)
    return _require(tenant_id, order_item_id)


def carry_forward(tenant_id, order_item_id, reviewed_by):
    _require(tenant_id, order_item_id)
    repo.set_pending_status(tenant_id, order_item_id, "carried", reviewed_by)
    return _require(tenant_id, order_item_id)


def bulk(tenant_id, refresh_id, action, order_item_ids, reviewed_by):
    """Apply one pending action (carry / skip / finalize) to many items at once —
    powers bulk processing and supplier-wise carry in the Pending tab."""
    status = _BULK_STATUS.get(action)
    if status is None:
        raise HTTPException(status_code=400, detail="Unknown pending action")
    processed = 0
    for order_item_id in order_item_ids:
        item = repo.get_item(tenant_id, order_item_id)
        if not item or str(item.get("refresh_id")) != str(refresh_id):
            continue
        repo.set_pending_status(tenant_id, order_item_id, status, reviewed_by)
        processed += 1
    logger.info("Pending bulk %s tenant=%s refresh=%s processed=%s by=%s",
                action, tenant_id, refresh_id, processed, reviewed_by)
    return {"action": action, "processed": processed}


def report_xlsx(tenant_id, refresh_id):
    """Server-generated pending report (.xlsx). Returns (bytes, filename)."""
    from openpyxl import Workbook  # local import: only needed for the report

    rows = repo.list_all_pending(tenant_id, refresh_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Pending"
    headers = [
        "Product Code", "Product Name", "Supplier", "Movement", "Stock Status",
        "Final Qty", "Received Qty", "Pending Qty", "Status",
    ]
    ws.append(headers)
    for r in rows:
        ws.append([
            r.get("product_code"),
            r.get("product_name"),
            r.get("supplier_code"),
            r.get("movement_class"),
            r.get("stock_status"),
            r.get("final_qty"),
            r.get("received_qty"),
            r.get("remaining_qty"),
            r.get("pending_status") or r.get("item_status"),
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"pending-{str(refresh_id)[:8]}.xlsx"


def finalize(tenant_id, refresh_id, reviewed_by):
    count = repo.finalize_all(tenant_id, refresh_id, reviewed_by)
    logger.info("Pending finalized tenant=%s refresh=%s count=%s by=%s",
                tenant_id, refresh_id, count, reviewed_by)
    return {"refresh_id": str(refresh_id), "finalized": count}


def add_manual(tenant_id, refresh_id, cycle_id, store_id,
               product_code, product_name, qty, created_by):
    if not product_code or not str(product_code).strip():
        raise HTTPException(status_code=400, detail="product_code is required")
    if qty is None or qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")
    existing = repo.get_item_by_product(tenant_id, refresh_id, product_code)
    if existing:
        # Idempotent: a retried/duplicate submission for a product already
        # working in this refresh returns the existing row instead of a 409 —
        # callers (including a rapid double-submit from the UI) always land
        # on the same order item rather than erroring or inserting a dupe.
        return {
            "order_item_id": existing["order_item_id"],
            "product_code": product_code,
            "is_manual": existing["is_manual"],
            "already_exists": True,
        }
    new_id = repo.add_manual_item(
        tenant_id, refresh_id, cycle_id, store_id,
        product_code, product_name, qty, created_by,
    )
    return {"order_item_id": new_id, "product_code": product_code, "is_manual": True}
