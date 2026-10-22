/* Rollback for 0026_procurement_rules_registry.sql.
   NOT APPLIED.

   Refuses to drop the snapshot pointer when any refresh already references
   a snapshot. Does not delete OrderHeaderDetails, VPL rows, or refresh rows.
   Drops only the registry tables and the nullable column added by 0026.
*/

IF OBJECT_ID('procurement.procurement_refreshes', 'U') IS NOT NULL
   AND COL_LENGTH('procurement.procurement_refreshes', 'rule_snapshot_id') IS NOT NULL
   AND EXISTS (
        SELECT 1
        FROM procurement.procurement_refreshes
        WHERE rule_snapshot_id IS NOT NULL
   )
BEGIN
    THROW 50026, 'Refusing rollback: a refresh already references a rule snapshot.', 1;
END
GO

IF COL_LENGTH('procurement.procurement_refreshes', 'rule_snapshot_id') IS NOT NULL
    ALTER TABLE procurement.procurement_refreshes DROP COLUMN rule_snapshot_id;
GO

IF OBJECT_ID('procurement.rule_effective_snapshot_item', 'U') IS NOT NULL
    DROP TABLE procurement.rule_effective_snapshot_item;
GO
IF OBJECT_ID('procurement.rule_effective_snapshot', 'U') IS NOT NULL
    DROP TABLE procurement.rule_effective_snapshot;
GO
IF OBJECT_ID('procurement.rule_change_audit', 'U') IS NOT NULL
    DROP TABLE procurement.rule_change_audit;
GO
IF OBJECT_ID('procurement.rule_store_override', 'U') IS NOT NULL
    DROP TABLE procurement.rule_store_override;
GO
IF OBJECT_ID('procurement.rule_default_revision', 'U') IS NOT NULL
    DROP TABLE procurement.rule_default_revision;
GO
IF OBJECT_ID('procurement.rule_definition', 'U') IS NOT NULL
    DROP TABLE procurement.rule_definition;
GO
