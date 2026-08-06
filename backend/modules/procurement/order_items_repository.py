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


def carry_forward_skips(conn, tenant_id, previous_refresh_id, refresh_id, store_id):
    """Re-apply a still-active skip from the previous Refresh onto the new one.

    Only 'until_next_sales' and 'until_next_demand' persist across refreshes;
    'current_refresh' is intentionally refresh-scoped and never carried. A skip
    stops applying the moment a real sale is recorded for the product after the
    skip was made (reviewed_at) — that's the "next sale" / "next demand" signal
    for both modes (manual un-skip on the new row covers the PM-re-adds case).
    Returns the number of new-refresh rows re-suppressed.
    """
    if not previous_refresh_id:
        return 0

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE noi
        SET item_status = 'skipped',
            skip_reason = poi.skip_reason,
            final_qty = 0,
            remaining_qty = 0,
            updated_at = GETDATE()
        FROM procurement.procurement_order_items noi
        INNER JOIN procurement.procurement_order_items poi
            ON poi.tenant_id = noi.tenant_id
           AND poi.refresh_id = ?
           AND poi.product_code = noi.product_code
           AND poi.is_deleted = 0
        WHERE noi.tenant_id = ?
          AND noi.refresh_id = ?
          AND noi.is_deleted = 0
          AND poi.item_status = 'skipped'
          AND poi.skip_reason IN ('until_next_sales', 'until_next_demand')
          AND NOT EXISTS (
              SELECT 1 FROM sync.ProductSaleInformation s
              WHERE s.store_id = ?
                AND CAST(s.ProductCode AS NVARCHAR(50)) = noi.product_code
                AND s.SeriesTransID = 1
                AND s.TransactionValidity = 0
                AND s.TransactionDate > poi.reviewed_at
          )
        """,
        (previous_refresh_id, tenant_id, refresh_id, store_id),
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
