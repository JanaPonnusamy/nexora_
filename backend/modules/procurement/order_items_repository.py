"""Data access for Working Order Items generation (Phase 4 orchestration).

Working Order Items are materialized directly from the immutable VPL: one row
per virtual product whose Decision-Engine suggested_qty > 0. Excluded products
(suggested_qty = 0 / NULL) never enter this table — they remain only in the VPL
snapshot for explainability.

This is a pure bulk copy of an already-computed decision (no business rules
here): a single INSERT ... SELECT, so there is no row-by-row insert and no data
round-trip. Runs on a caller-owned connection/transaction.
"""

from modules.procurement._dbutil import as_uid as _as_uid


def clear_working_items(conn, tenant_id, refresh_id):
    """Remove any prior working items for the Refresh (deterministic re-gen)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM procurement.procurement_order_items
        WHERE refresh_id = ? AND tenant_id = ?
        """,
        (refresh_id, tenant_id),
    )
    return cursor.rowcount


def generate_working_items(conn, tenant_id, refresh_id, store_id, created_by):
    """Bulk-create working items from the VPL where suggested_qty > 0.

    final_qty seeds from the engine's suggested_qty; remaining_qty (= Pending)
    starts equal to final_qty; assigned_qty starts at 0; status 'draft'.
    Returns the number of working items created.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.procurement_order_items
            (tenant_id, cycle_id, refresh_id, store_id,
             product_id, product_code,
             suggested_qty, final_qty, assigned_qty, remaining_qty,
             item_status, created_by)
        SELECT
            vp.tenant_id, vp.cycle_id, vp.refresh_id, ?,
            vp.product_id, vp.product_code,
            vp.suggested_qty, vp.suggested_qty, 0, vp.suggested_qty,
            'draft', ?
        FROM procurement.procurement_virtual_products vp
        WHERE vp.tenant_id = ?
          AND vp.refresh_id = ?
          AND vp.suggested_qty > 0
        """,
        (store_id, _as_uid(created_by), tenant_id, refresh_id),
    )
    return cursor.rowcount


def count_working_items(conn, tenant_id, refresh_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM procurement.procurement_order_items
        WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (refresh_id, tenant_id),
    )
    return cursor.fetchone()[0]
