/* Verification for 0026. Run only against the database where 0026 was applied.
   Expected: one row, ok = 1. This file was not executed in the workspace
   because no isolated SQL Server test database was verified.
*/

SELECT
    CASE
        WHEN OBJECT_ID('procurement.rule_definition', 'U') IS NULL THEN 0
        WHEN OBJECT_ID('procurement.rule_default_revision', 'U') IS NULL THEN 0
        WHEN OBJECT_ID('procurement.rule_store_override', 'U') IS NULL THEN 0
        WHEN OBJECT_ID('procurement.rule_change_audit', 'U') IS NULL THEN 0
        WHEN OBJECT_ID('procurement.rule_effective_snapshot', 'U') IS NULL THEN 0
        WHEN OBJECT_ID('procurement.rule_effective_snapshot_item', 'U') IS NULL THEN 0
        WHEN COL_LENGTH('procurement.procurement_refreshes', 'rule_snapshot_id') IS NULL THEN 0
        WHEN COLUMNPROPERTY(OBJECT_ID('procurement.procurement_refreshes'), 'rule_snapshot_id', 'AllowsNull') <> 1 THEN 0
        ELSE 1
    END AS ok;
