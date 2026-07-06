"""Data access for Pending Management (Sprint 3, Module 3).

Pending is NOT a table — it is order items with remaining_qty > 0. This module
lists those rows and records the pending-review outcome (adjust / skip / carry
forward / finalize) plus manual procurement additions. Caller-owned or own
connection as noted.
"""

from config.database import get_connection
from modules.procurement._dbutil import (
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
    as_uid as _as_uid,
)


# Primary supplier for the pending line — the most recent assignment's supplier,
# so the Pending tab can group / carry pending supplier-wise.
_SUPPLIER_SUBQUERY = (
    "(SELECT TOP 1 a.supplier_code "
    " FROM procurement.procurement_order_item_assignments a "
    " WHERE a.order_item_id = oi.order_item_id AND a.is_deleted = 0 "
    " ORDER BY a.created_at DESC) AS supplier_code"
)

_SELECT = """
    oi.order_item_id, oi.tenant_id, oi.cycle_id, oi.refresh_id, oi.store_id,
    oi.product_id, oi.product_code, oi.is_manual,
    oi.suggested_qty, oi.final_qty, oi.assigned_qty, oi.received_qty,
    oi.remaining_qty, oi.item_status, oi.pending_status, oi.skip_reason,
    vp.product_name, vp.movement_class, vp.stock_status,
""" + _SUPPLIER_SUBQUERY

_FROM_JOIN = (
    "FROM procurement.procurement_order_items oi "
    "LEFT JOIN procurement.procurement_virtual_products vp "
    "  ON vp.tenant_id = oi.tenant_id AND vp.refresh_id = oi.refresh_id "
    "  AND vp.product_id = oi.product_id"
)

_PENDING_WHERE = [
    "oi.tenant_id = ?", "oi.refresh_id = ?", "oi.is_deleted = 0",
    "oi.remaining_qty > 0", "oi.item_status <> 'skipped'",
]


def list_pending(tenant_id, refresh_id, page, page_size):
    where_sql = " AND ".join(_PENDING_WHERE)
    params = [tenant_id, refresh_id]
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) {_FROM_JOIN} WHERE {where_sql}", params)
        total = cursor.fetchone()[0]
        cursor.execute(
            f"SELECT {_SELECT} {_FROM_JOIN} WHERE {where_sql} "
            "ORDER BY supplier_code, oi.product_code "
            "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            params + [offset, page_size],
        )
        items = [_stringify(r) for r in _rows_to_dicts(cursor)]
        return items, total
    finally:
        conn.close()


def list_all_pending(tenant_id, refresh_id):
    """Every pending line for a refresh (unpaged) — used by the pending report."""
    where_sql = " AND ".join(_PENDING_WHERE)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_SELECT} {_FROM_JOIN} WHERE {where_sql} "
            "ORDER BY supplier_code, oi.product_code",
            [tenant_id, refresh_id],
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def get_item(tenant_id, order_item_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT order_item_id, tenant_id, cycle_id, refresh_id, store_id, "
            "product_id, product_code, final_qty, remaining_qty, item_status, "
            "pending_status "
            "FROM procurement.procurement_order_items "
            "WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0",
            (tenant_id, order_item_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def _run(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        affected = cursor.rowcount
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def adjust_pending(tenant_id, order_item_id, remaining_qty, reviewed_by):
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET remaining_qty = ?, pending_status = 'reviewed',
            reviewed_by = ?, reviewed_at = GETDATE(), updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (remaining_qty, _as_uid(reviewed_by), tenant_id, order_item_id),
    )


def set_pending_status(tenant_id, order_item_id, status, reviewed_by):
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET pending_status = ?,
            reviewed_by = ?, reviewed_at = GETDATE(), updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (status, _as_uid(reviewed_by), tenant_id, order_item_id),
    )


def finalize_all(tenant_id, refresh_id, reviewed_by):
    """Finalize every still-open pending row that wasn't explicitly resolved."""
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET pending_status = 'finalized',
            reviewed_by = ?, reviewed_at = GETDATE(), updated_at = GETDATE()
        WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
          AND remaining_qty > 0 AND item_status <> 'skipped'
          AND (pending_status IS NULL OR pending_status = 'reviewed')
        """,
        (_as_uid(reviewed_by), tenant_id, refresh_id),
    )


def add_manual_item(tenant_id, refresh_id, cycle_id, store_id,
                    product_code, product_name, qty, created_by):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO procurement.procurement_order_items
                (tenant_id, cycle_id, refresh_id, store_id, product_id,
                 product_code, suggested_qty, final_qty, assigned_qty,
                 remaining_qty, item_status, is_manual, created_by)
            OUTPUT INSERTED.order_item_id
            VALUES (?, ?, ?, ?, NEWID(), ?, 0, ?, 0, ?, 'review', 1, ?)
            """,
            (tenant_id, cycle_id, refresh_id, store_id, product_code,
             qty, qty, _as_uid(created_by)),
        )
        new_id = str(cursor.fetchone()[0])
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def product_already_in_refresh(tenant_id, refresh_id, product_code):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM procurement.procurement_order_items
            WHERE tenant_id = ? AND refresh_id = ? AND product_code = ?
              AND is_deleted = 0
            """,
            (tenant_id, refresh_id, product_code),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()
