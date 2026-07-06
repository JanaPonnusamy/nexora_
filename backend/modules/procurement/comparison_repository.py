"""Data access for Next-Refresh carry-forward (Sprint 3, Module 4).

Reads the previous Refresh's carried pending and seeds it into the new Refresh's
working items. Completed items are excluded by the WHERE clause (remaining > 0).
Caller-owned transaction.
"""

from modules.procurement._dbutil import as_uid as _as_uid


def carried_pending(conn, tenant_id, previous_refresh_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT product_code, product_id, remaining_qty
        FROM procurement.procurement_order_items
        WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
          AND remaining_qty > 0 AND pending_status = 'carried'
          AND item_status <> 'skipped'
        """,
        (tenant_id, previous_refresh_id),
    )
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, r)) for r in cursor.fetchall()]


def exists_in_refresh(conn, tenant_id, refresh_id, product_code):
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


def insert_carried(conn, tenant_id, refresh, product_code, product_id, qty, created_by):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.procurement_order_items
            (tenant_id, cycle_id, refresh_id, store_id, product_id, product_code,
             suggested_qty, final_qty, assigned_qty, remaining_qty,
             item_status, pending_status, is_manual, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'review', 'carried', 0, ?)
        """,
        (tenant_id, refresh["cycle_id"], refresh["refresh_id"],
         refresh.get("store_id"), product_id, product_code,
         qty, qty, qty, _as_uid(created_by)),
    )
    return cursor.rowcount
