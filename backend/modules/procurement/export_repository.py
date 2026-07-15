"""Data access for Supplier Export (Sprint 2, Module 6).

Export is NOT a separate entity: there is no Export Header. Export metadata lives
on procurement_order_item_assignments (export_batch_number / split / uid /
exported_at / exported_by). Multiple exports are allowed — each run stamps a new
batch onto the then-unexported ('draft') assignments. Export history is read
back from these records. Writes run on a caller-owned transaction.
"""

from config.database import get_connection
from modules.procurement._dbutil import as_uid as _as_uid, rows_to_dicts as _rows_to_dicts


def exportable_assignments(conn, tenant_id, refresh_id, assignment_ids=None, supplier_code=None):
    """Draft (unexported), valid assignments for a Refresh — optionally a subset.

    Always reads live from procurement_order_item_assignments (no caching
    layer anywhere in this path) — a call with neither filter, or with only
    supplier_code, resolves the CURRENT full set at request time, so it can
    never return a stale or empty result while real assignments exist (§14).
    """
    sql = (
        "SELECT assignment_id, order_item_id, supplier_code, assigned_qty "
        "FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0 "
        "AND assignment_status = 'draft' "
        "AND supplier_code IS NOT NULL AND assigned_qty > 0"
    )
    params = [tenant_id, refresh_id]
    if assignment_ids:
        placeholders = ", ".join(["?"] * len(assignment_ids))
        sql += f" AND assignment_id IN ({placeholders})"
        params.extend(assignment_ids)
    elif supplier_code:
        sql += " AND supplier_code = ?"
        params.append(supplier_code)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return _rows_to_dicts(cursor)


def all_assignment_items(conn, tenant_id, refresh_id):
    """Every live, valid assignment for a Refresh (assignment_id + qty),
    regardless of export status — the complete picking order the Shelf Sorting
    screen sorts and splits. Reads live so it always reflects the current set.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT assignment_id, assigned_qty "
        "FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0 "
        "AND supplier_code IS NOT NULL AND assigned_qty > 0",
        (tenant_id, refresh_id),
    )
    return _rows_to_dicts(cursor)


def mark_exported(conn, tenant_id, assignment_id, batch_no, split_no, uid, exported_by):
    exported_by = _as_uid(exported_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET assignment_status = 'exported',
            export_batch_number = ?, export_split_number = ?, export_uid = ?,
            exported_at = GETDATE(), exported_by = ?,
            updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (batch_no, split_no, uid, exported_by, exported_by,
         tenant_id, assignment_id),
    )
    return cursor.rowcount


def export_history(tenant_id, refresh_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT export_batch_number,
                   MIN(exported_at)              AS exported_at,
                   COUNT(*)                      AS line_count,
                   COUNT(DISTINCT supplier_code) AS supplier_count,
                   SUM(assigned_qty)             AS total_qty
            FROM procurement.procurement_order_item_assignments
            WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
              AND export_batch_number IS NOT NULL
            GROUP BY export_batch_number
            ORDER BY MIN(exported_at) DESC
            """,
            (tenant_id, refresh_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def export_batch_detail(tenant_id, batch_no):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT assignment_id, order_item_id, product_code, supplier_code,
                   assigned_qty, export_split_number, export_uid,
                   exported_at, exported_by
            FROM procurement.procurement_order_item_assignments
            WHERE tenant_id = ? AND export_batch_number = ? AND is_deleted = 0
            ORDER BY export_split_number, supplier_code
            """,
            (tenant_id, batch_no),
        )
        rows = _rows_to_dicts(cursor)
        return [
            {k: (str(v) if (k.endswith("_id") or k.endswith("_by")) and v is not None else v)
             for k, v in r.items()}
            for r in rows
        ]
    finally:
        conn.close()
