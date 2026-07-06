"""Read-only VPL comparison queries — runtime operation, no persistence.

Comparison is NOT a business entity: there is no compare_session, compare table
or comparison history. Two immutable VPL snapshots are compared on the fly with
a single optimised SQL query (FULL OUTER JOIN on product_id). This module only
ever SELECTs — never INSERT / UPDATE / DELETE.
"""

from config.database import get_connection

# The canonical procurement quantity compared between snapshots. final_required_qty
# is the legacy order_virtual_items engine output; NULL (pre-calculation) is
# treated as 0 for difference purposes.
_QTY = "final_required_qty"

_VALID_ACTIONS = {"Added", "Removed", "Increased", "Decreased", "NoChange"}


def read_comparison(tenant_id, source_vpl_id, target_vpl_id,
                    changed_only, action_filter, search, page, page_size):
    """Compare two VPL snapshots in a single query.

    Returns (items, total). total is the count AFTER filters (COUNT(*) OVER),
    so the whole comparison + pagination is one round-trip — the dataset is
    never materialised in Python.
    """
    filters = []
    params = [
        tenant_id, source_vpl_id,   # source snapshot
        tenant_id, target_vpl_id,   # target snapshot
    ]

    if changed_only:
        filters.append("change_type <> 'NoChange'")
    if action_filter:
        filters.append("change_type = ?")
        params.append(action_filter)
    if search:
        filters.append("(product_code LIKE ? OR product_name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    filter_sql = (" AND " + " AND ".join(filters)) if filters else ""
    offset = (page - 1) * page_size
    params.extend([offset, page_size])

    sql = f"""
        WITH cmp AS (
            SELECT
                COALESCE(s.product_id, t.product_id)      AS product_id,
                COALESCE(t.product_code, s.product_code)  AS product_code,
                COALESCE(t.product_name, s.product_name)  AS product_name,
                s.{_QTY}                                  AS source_qty,
                t.{_QTY}                                  AS target_qty,
                (COALESCE(t.{_QTY}, 0) - COALESCE(s.{_QTY}, 0)) AS qty_difference,
                CASE
                    WHEN s.product_id IS NULL THEN 'Added'
                    WHEN t.product_id IS NULL THEN 'Removed'
                    WHEN COALESCE(t.{_QTY}, 0) > COALESCE(s.{_QTY}, 0)
                        THEN 'Increased'
                    WHEN COALESCE(t.{_QTY}, 0) < COALESCE(s.{_QTY}, 0)
                        THEN 'Decreased'
                    ELSE 'NoChange'
                END AS change_type
            FROM (
                SELECT product_id, product_code, product_name, {_QTY}
                FROM procurement.procurement_virtual_products
                WHERE tenant_id = ? AND refresh_id = ?
            ) s
            FULL OUTER JOIN (
                SELECT product_id, product_code, product_name, {_QTY}
                FROM procurement.procurement_virtual_products
                WHERE tenant_id = ? AND refresh_id = ?
            ) t
                ON s.product_id = t.product_id
        )
        SELECT
            product_id, product_code, product_name,
            source_qty, target_qty, qty_difference, change_type,
            COUNT(*) OVER() AS total_count
        FROM cmp
        WHERE 1 = 1{filter_sql}
        ORDER BY product_code
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
    finally:
        conn.close()

    total = rows[0]["total_count"] if rows else 0
    items = []
    for r in rows:
        r.pop("total_count", None)
        if r.get("product_id") is not None:
            r["product_id"] = str(r["product_id"])
        items.append(r)
    return items, total
