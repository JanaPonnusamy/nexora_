/* Rollback 0030_vpl_history_persistence.sql. Run manually against NEXORA_PLATFORM.
   Refuses to drop row_version columns if any row has moved past its default
   (1) — that would silently discard concurrency state relied on by live
   optimistic-concurrency checks. Refuses to drop the history/removed tables
   if they contain any rows — this is archival/audit data, not disposable.

   IMPORTANT (found by real-SQL-Server integration testing, 2026-10-21):
   RAISERROR + RETURN only exits the CURRENT GO batch in sqlcmd — it does
   NOT stop later batches in the same script. The original version of this
   file printed the refusal error but then dropped the tables/columns
   anyway, because each GO-separated block ran independently. Fixed the
   same way as 0028's rollback: a #temp table set once, checked at the top
   of every later batch, so "refuse" actually means "do nothing" for the
   rest of the script, not just the first batch.
*/

IF OBJECT_ID('tempdb..#rollback_0030_guard') IS NOT NULL DROP TABLE #rollback_0030_guard;
SELECT CAST(
    CASE WHEN
        EXISTS (SELECT 1 FROM procurement.procurement_order_items WHERE row_version <> 1)
        OR EXISTS (SELECT 1 FROM procurement.procurement_order_item_assignments WHERE row_version <> 1)
        OR EXISTS (SELECT 1 FROM procurement.procurement_refreshes WHERE row_version <> 1)
        OR EXISTS (SELECT 1 FROM procurement.vpl_history_batch)
        OR EXISTS (SELECT 1 FROM procurement.vpl_removed_line)
    THEN 1 ELSE 0 END AS BIT
) AS blocked
INTO #rollback_0030_guard;

IF EXISTS (SELECT 1 FROM #rollback_0030_guard WHERE blocked = 1)
    RAISERROR('Refusing rollback: row_version has advanced and/or history/removed-line tables contain data.', 16, 1);
GO

IF NOT EXISTS (SELECT 1 FROM #rollback_0030_guard WHERE blocked = 1)
BEGIN
    IF OBJECT_ID('procurement.vpl_history_assignment', 'U') IS NOT NULL
        DROP TABLE procurement.vpl_history_assignment;
    IF OBJECT_ID('procurement.vpl_history_line', 'U') IS NOT NULL
        DROP TABLE procurement.vpl_history_line;
    IF OBJECT_ID('procurement.vpl_history_batch', 'U') IS NOT NULL
        DROP TABLE procurement.vpl_history_batch;
    IF OBJECT_ID('procurement.vpl_removed_line', 'U') IS NOT NULL
        DROP TABLE procurement.vpl_removed_line;
END
GO

IF NOT EXISTS (SELECT 1 FROM #rollback_0030_guard WHERE blocked = 1)
BEGIN
    IF COL_LENGTH('procurement.procurement_refreshes', 'row_version') IS NOT NULL
        ALTER TABLE procurement.procurement_refreshes DROP COLUMN row_version;
    IF COL_LENGTH('procurement.procurement_order_item_assignments', 'row_version') IS NOT NULL
        ALTER TABLE procurement.procurement_order_item_assignments DROP COLUMN row_version;
    IF COL_LENGTH('procurement.procurement_order_items', 'row_version') IS NOT NULL
        ALTER TABLE procurement.procurement_order_items DROP COLUMN row_version;
END
GO

DROP TABLE #rollback_0030_guard;
GO
