"""Data access for Supplier Reply import (Sprint: Export Monitor overhaul).

A pre-shipment supplier confirmation (Status + Available Qty on the returned
Excel) — deliberately separate from reconciliation_repository, which owns the
real GRN-receipt state machine (received_qty/grn_no/assignment_status driven
by actual synced sync.PurchaseTrans receipts). This module only ever touches
supplier_reply_* columns plus, for a shortfall, the order item's remaining_qty
— never assignment_status/received_qty.
"""

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)


def get_assignments_by_ids(tenant_id, assignment_ids):
    """Live assignments for preview — includes product_name via the owning
    order item's VPL row so the confirm screen can show something readable
    even when the sheet's own Product Name text was edited by the supplier."""
    if not assignment_ids:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        placeholders = ", ".join("?" for _ in assignment_ids)
        cursor.execute(
            f"""
            SELECT a.assignment_id, a.order_item_id, a.product_code, a.supplier_code,
                   a.assigned_qty, a.assignment_status, vp.product_name
            FROM procurement.procurement_order_item_assignments a
            LEFT JOIN procurement.procurement_order_items oi ON oi.order_item_id = a.order_item_id
            LEFT JOIN procurement.procurement_virtual_products vp
                ON vp.tenant_id = oi.tenant_id AND vp.refresh_id = oi.refresh_id
               AND vp.product_id = oi.product_id
            WHERE a.tenant_id = ? AND a.assignment_id IN ({placeholders}) AND a.is_deleted = 0
            """,
            (tenant_id, *assignment_ids),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def get_assignment(conn, tenant_id, assignment_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT assignment_id, order_item_id, assigned_qty
        FROM procurement.procurement_order_item_assignments
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (tenant_id, assignment_id),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {"assignment_id": str(row[0]), "order_item_id": str(row[1]), "assigned_qty": row[2]}


def apply_reply(conn, tenant_id, assignment_id, status, qty, replied_by):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET supplier_reply_status = ?, supplier_reply_qty = ?,
            supplier_reply_at = GETDATE(), supplier_reply_by = ?
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (status, qty, _as_uid(replied_by), tenant_id, assignment_id),
    )
    return cursor.rowcount


def mark_shortfall(conn, tenant_id, order_item_id, remaining_qty):
    """Surfaces the order item in the existing Pending tab (its
    ``remaining_qty > 0 AND item_status <> 'skipped'`` predicate) with zero
    Pending-module changes — deliberately does not touch item_status or
    received_qty, which stay owned by the real GRN reconciliation path."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_items
        SET remaining_qty = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (remaining_qty, tenant_id, order_item_id),
    )
    return cursor.rowcount
