/* Verify 0028_rare_mover_confirmation.sql. Run manually against NEXORA_PLATFORM. */

SELECT
    COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed')     AS has_rare_confirmed,
    COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed_by') AS has_rare_confirmed_by,
    COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed_at') AS has_rare_confirmed_at;
-- Expect all three NOT NULL (column exists).

SELECT COUNT(*) AS rows_with_bad_default
FROM procurement.procurement_order_items
WHERE rare_confirmed IS NULL;
-- Expect 0 — NOT NULL DEFAULT 0 means no existing row can be NULL.
