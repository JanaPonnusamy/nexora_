"""Data access for Supplier Assignment (Sprint 2, Module 5).

One order item may receive several assignments (partial / multi-supplier). All
writes run on a caller-owned connection so a bulk assignment is atomic. After
any assignment change the owning order item's assigned_qty / remaining_qty /
item_status are recomputed from the live assignments (single source of truth —
no duplicated totals).
"""

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)


_ASSIGN_COLS = """
    assignment_id, tenant_id, cycle_id, refresh_id, order_item_id, store_id,
    product_code, supplier_code, assigned_qty, assignment_status, remarks,
    export_batch_number, export_split_number, export_uid, exported_at, exported_by,
    received_qty, grn_no, supplier_bill_no, created_by, created_at
"""


# --------------------------------------------------------------------------
# reads (own connection)
# --------------------------------------------------------------------------

def get_assignment(tenant_id, assignment_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_ASSIGN_COLS} "
            "FROM procurement.procurement_order_item_assignments "
            "WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0",
            (tenant_id, assignment_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_by_order_item(tenant_id, order_item_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_ASSIGN_COLS} "
            "FROM procurement.procurement_order_item_assignments "
            "WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0 "
            "ORDER BY created_at",
            (tenant_id, order_item_id),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# transactional checks/writes (caller-owned connection)
# --------------------------------------------------------------------------

def active_assigned_total(conn, tenant_id, order_item_id, exclude_assignment_id=None):
    """SUM of live assigned quantities for an order item."""
    sql = (
        "SELECT COALESCE(SUM(assigned_qty), 0) "
        "FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0"
    )
    params = [tenant_id, order_item_id]
    if exclude_assignment_id is not None:
        sql += " AND assignment_id <> ?"
        params.append(exclude_assignment_id)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchone()[0] or 0


def duplicate_active_exists(conn, tenant_id, order_item_id, supplier_code,
                            exclude_assignment_id=None):
    sql = (
        "SELECT 1 FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND order_item_id = ? AND supplier_code = ? "
        "AND is_deleted = 0"
    )
    params = [tenant_id, order_item_id, supplier_code]
    if exclude_assignment_id is not None:
        sql += " AND assignment_id <> ?"
        params.append(exclude_assignment_id)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchone() is not None


def insert_assignment(conn, item, supplier_code, qty, remarks, created_by):
    created_by = _as_uid(created_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.procurement_order_item_assignments
            (tenant_id, cycle_id, refresh_id, order_item_id, store_id,
             product_code, supplier_code, assigned_qty, assignment_status,
             remarks, created_by)
        OUTPUT INSERTED.assignment_id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """,
        (
            item["tenant_id"], item["cycle_id"], item["refresh_id"],
            item["order_item_id"], item.get("store_id"),
            item.get("product_code"), supplier_code, qty, remarks, created_by,
        ),
    )
    return str(cursor.fetchone()[0])


def update_supplier(conn, tenant_id, assignment_id, supplier_code, updated_by):
    updated_by = _as_uid(updated_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET supplier_code = ?, updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (supplier_code, updated_by, tenant_id, assignment_id),
    )
    return cursor.rowcount


def update_qty(conn, tenant_id, assignment_id, qty, updated_by):
    updated_by = _as_uid(updated_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET assigned_qty = ?, updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (qty, updated_by, tenant_id, assignment_id),
    )
    return cursor.rowcount


def soft_delete(conn, tenant_id, assignment_id, deleted_by):
    deleted_by = _as_uid(deleted_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET is_deleted = 1, deleted_at = GETDATE(), deleted_by = ?
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (deleted_by, tenant_id, assignment_id),
    )
    return cursor.rowcount


def recompute_order_item(conn, tenant_id, order_item_id):
    """Re-derive assigned_qty / remaining_qty / item_status from live assignments."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE oi
        SET assigned_qty = x.total,
            remaining_qty = oi.final_qty - x.total,
            item_status = CASE
                WHEN oi.item_status = 'skipped' THEN 'skipped'
                WHEN x.total <= 0 AND oi.manual_override = 1 THEN 'review'
                WHEN x.total <= 0 THEN 'draft'
                WHEN x.total >= oi.final_qty THEN 'assigned'
                ELSE 'partial' END,
            updated_at = GETDATE()
        FROM procurement.procurement_order_items oi
        CROSS APPLY (
            SELECT COALESCE(SUM(a.assigned_qty), 0) AS total
            FROM procurement.procurement_order_item_assignments a
            WHERE a.order_item_id = oi.order_item_id AND a.is_deleted = 0
        ) x
        WHERE oi.tenant_id = ? AND oi.order_item_id = ? AND oi.is_deleted = 0
        """,
        (tenant_id, order_item_id),
    )
