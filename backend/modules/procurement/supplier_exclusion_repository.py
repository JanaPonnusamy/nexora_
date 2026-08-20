"""Cross-cycle supplier exclusions (Sprint: Export Monitor overhaul).

A supplier that replied Partial/Not Available on a product, unresolved by the
time its cycle closes, is recorded here so Auto Assign / Rank Assign stop
offering that supplier for that product on the NEXT cycle (owner-directed:
"next order this product not assign to this supplier"). Read side lives in
supplier_repository (the NOT EXISTS predicate on top_suppliers/top_suppliers_bulk).
"""

from config.database import get_connection


def record_exclusions_from_replies(conn, tenant_id, cycle_id):
    """Insert one exclusion row per (supplier, product) with an unresolved
    partial/not_available reply in this cycle — skips pairs already recorded
    (UX_supplier_product_exclusions). Returns the number of rows inserted."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.supplier_product_exclusions
            (tenant_id, store_id, supplier_code, product_code, reason, cycle_id)
        SELECT DISTINCT a.tenant_id, a.store_id, a.supplier_code, a.product_code,
               a.supplier_reply_status, ?
        FROM procurement.procurement_order_item_assignments a
        WHERE a.tenant_id = ? AND a.cycle_id = ? AND a.is_deleted = 0
          AND a.supplier_reply_status IN ('partial', 'not_available')
          AND NOT EXISTS (
              SELECT 1 FROM procurement.supplier_product_exclusions ex
              WHERE ex.tenant_id = a.tenant_id AND ex.store_id = a.store_id
                AND ex.supplier_code = a.supplier_code AND ex.product_code = a.product_code
          )
        """,
        (cycle_id, tenant_id, cycle_id),
    )
    return cursor.rowcount


def list_for_store(tenant_id, store_id):
    """All current exclusions for a store — diagnostic/admin use."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT supplier_code, product_code, reason, created_at
            FROM procurement.supplier_product_exclusions
            WHERE tenant_id = ? AND store_id = ?
            ORDER BY created_at DESC
            """,
            (tenant_id, store_id),
        )
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()
