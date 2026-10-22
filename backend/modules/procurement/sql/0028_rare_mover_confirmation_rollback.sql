/* Rollback 0028_rare_mover_confirmation.sql. Run manually against NEXORA_PLATFORM.
   Refuses when any row has rare_confirmed = 1 — dropping the column would
   silently discard confirmation evidence that may be relied on by an
   in-flight assignment/export decision.

   IMPORTANT (found by real-SQL-Server integration testing, 2026-10-21):
   RAISERROR + RETURN only exits the CURRENT GO batch in sqlcmd — it does
   NOT stop later batches in the same script from running. An earlier
   version of this file put the guard in its own batch, separated by GO
   from the DROP COLUMN statements, so the refusal printed an error but the
   columns were dropped anyway. Fixed by checking a #temp table (visible
   across GO batches on the same session) at the top of every later batch
   instead of relying on RETURN to stop execution.
*/

IF OBJECT_ID('tempdb..#rollback_0028_guard') IS NOT NULL DROP TABLE #rollback_0028_guard;
SELECT CAST(
    CASE WHEN EXISTS (SELECT 1 FROM procurement.procurement_order_items WHERE rare_confirmed = 1)
         THEN 1 ELSE 0 END AS BIT
) AS blocked
INTO #rollback_0028_guard;

IF EXISTS (SELECT 1 FROM #rollback_0028_guard WHERE blocked = 1)
    RAISERROR('Refusing rollback: at least one row has rare_confirmed = 1.', 16, 1);
GO

IF NOT EXISTS (SELECT 1 FROM #rollback_0028_guard WHERE blocked = 1)
BEGIN
    IF COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed_at') IS NOT NULL
        ALTER TABLE procurement.procurement_order_items DROP COLUMN rare_confirmed_at;
END
GO
IF NOT EXISTS (SELECT 1 FROM #rollback_0028_guard WHERE blocked = 1)
BEGIN
    IF COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed_by') IS NOT NULL
        ALTER TABLE procurement.procurement_order_items DROP COLUMN rare_confirmed_by;
END
GO
IF NOT EXISTS (SELECT 1 FROM #rollback_0028_guard WHERE blocked = 1)
BEGIN
    IF COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed') IS NOT NULL
    BEGIN
        DECLARE @constraint_name NVARCHAR(200);
        SELECT @constraint_name = dc.name
        FROM sys.default_constraints dc
        JOIN sys.columns c
            ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = OBJECT_ID('procurement.procurement_order_items')
          AND c.name = 'rare_confirmed';
        IF @constraint_name IS NOT NULL
            EXEC('ALTER TABLE procurement.procurement_order_items DROP CONSTRAINT ' + @constraint_name);
        ALTER TABLE procurement.procurement_order_items DROP COLUMN rare_confirmed;
    END
END
GO

DROP TABLE #rollback_0028_guard;
GO
