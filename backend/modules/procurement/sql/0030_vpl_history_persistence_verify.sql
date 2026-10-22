/* Verify 0030_vpl_history_persistence.sql. Run manually against NEXORA_PLATFORM. */

SELECT OBJECT_ID('procurement.vpl_history_batch', 'U')      AS has_batch,
       OBJECT_ID('procurement.vpl_history_line', 'U')       AS has_line,
       OBJECT_ID('procurement.vpl_history_assignment', 'U') AS has_assignment_child,
       OBJECT_ID('procurement.vpl_removed_line', 'U')       AS has_removed_line;
-- Expect all four NOT NULL.

SELECT COL_LENGTH('procurement.procurement_order_items', 'row_version')            AS oi_row_version,
       COL_LENGTH('procurement.procurement_order_item_assignments', 'row_version') AS asg_row_version,
       COL_LENGTH('procurement.procurement_refreshes', 'row_version')              AS refresh_row_version;
-- Expect all three NOT NULL.

SELECT COUNT(*) AS duplicate_active_removed_lines
FROM procurement.vpl_removed_line
WHERE restored_at IS NULL
GROUP BY tenant_id, store_id, cycle_id, product_id
HAVING COUNT(*) > 1;
-- Expect 0 rows — the filtered unique index should already prevent this.

SELECT COUNT(*) AS duplicate_history_batches
FROM procurement.vpl_history_batch
GROUP BY tenant_id, source_refresh_id, successor_refresh_id
HAVING COUNT(*) > 1;
-- Expect 0 rows.
