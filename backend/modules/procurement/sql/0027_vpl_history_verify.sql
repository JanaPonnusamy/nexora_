/* Verification for 0027. Not executed. Expected ok = 1 after an approved apply. */

SELECT
    CASE
        WHEN OBJECT_ID('procurement.vpl_history_batch', 'U') IS NULL THEN 0
        WHEN OBJECT_ID('procurement.vpl_history_line', 'U') IS NULL THEN 0
        WHEN COL_LENGTH('procurement.procurement_order_items', 'row_version') IS NULL THEN 0
        WHEN COL_LENGTH('procurement.procurement_cycles', 'cycle_id') IS NULL THEN 0
        ELSE 1
    END AS ok;
