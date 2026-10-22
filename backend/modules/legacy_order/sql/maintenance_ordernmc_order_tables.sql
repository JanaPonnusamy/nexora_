/*
 * OrderNMC maintenance: Order Management table family.
 *
 * Context: OrderManagementBackup rows with OrderDate/WantedDate before
 * 2026-04-01 were already manually deleted by the operator. This script:
 *   1. Adds missing StoreName-leading indexes on tables that had none
 *      (OrderManagementHO, OrderPurchaseTrans) so store-scoped lookups don't
 *      scan the whole table -- matches the convention set by 0006's
 *      IX_PurchaseTrans_StoreName_ID / IX_PSI_Order_StoreSeriesValidityDate.
 *   2. Rebuilds every index (and heap table, via ALTER TABLE...REBUILD) on
 *      the Order Management table family to reclaim space/fragmentation
 *      left by the bulk delete.
 *   3. Shrinks the OrderNMC data file to release the freed pages back to
 *      the OS.
 *   4. Truncates the transaction log (checkpoint + shrink) -- safe only if
 *      OrderNMC is SIMPLE recovery model; this script checks and skips the
 *      log shrink with a warning if it is not. OrderNMC is FULL recovery,
 *      so this always no-ops here; the log is small anyway (<1MB used of
 *      256MB) so there is nothing worth reclaiming.
 *
 * IMPORTANT ORDERING, confirmed by hand on 2026-10-21: DBCC SHRINKFILE
 * physically compacts the data file by moving allocated pages toward the
 * front, which RE-FRAGMENTS every index it touches (this is documented
 * SQL Server behaviour, not a bug). Rebuild indexes FIRST, shrink LAST,
 * and do not shrink again afterward -- a second shrink will re-fragment
 * everything you just fixed for no space benefit once the file is already
 * at its live-data floor. If you must run both, this script's ordering
 * (rebuild everything, including heaps, then shrink once at the very end)
 * is correct; do not loop it.
 *
 * Scope is deliberately limited to the Order Management family, not every
 * table in OrderNMC (100+ tables, many unrelated: sync_*, *_Stage_*, audit,
 * etc.) -- confirmed with the operator before running.
 *
 * Run as the sa/admin login already used by backend/.env (DB_SERVER,
 * DB_USERNAME, DB_PASSWORD), against database OrderNMC.
 */

USE OrderNMC;
SET NOCOUNT ON;

PRINT '--- Step 1: add missing StoreName-leading indexes ---';

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.OrderManagementHO') AND name = 'IX_OrderManagementHO_StoreName_OrderId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_OrderManagementHO_StoreName_OrderId
        ON dbo.OrderManagementHO (StoreName, OrderId);
    PRINT 'Created IX_OrderManagementHO_StoreName_OrderId';
END

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.OrderPurchaseTrans') AND name = 'IX_OrderPurchaseTrans_StoreName_ProductCode'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_OrderPurchaseTrans_StoreName_ProductCode
        ON dbo.OrderPurchaseTrans (StoreName, ProductCode);
    PRINT 'Created IX_OrderPurchaseTrans_StoreName_ProductCode';
END

-- PurchaseTrans4Order's clustered PK is (ID, ProductCode, StoreName) --
-- StoreName trails, so store-scoped queries still benefit from a
-- StoreName-leading nonclustered index.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.PurchaseTrans4Order') AND name = 'IX_PurchaseTrans4Order_StoreName_ProductCode'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_PurchaseTrans4Order_StoreName_ProductCode
        ON dbo.PurchaseTrans4Order (StoreName, ProductCode);
    PRINT 'Created IX_PurchaseTrans4Order_StoreName_ProductCode';
END

PRINT '--- Step 1b: rebuild heap tables (no clustered index to carry the rebuild) ---';

IF OBJECT_ID('dbo.OrderManagement') IS NOT NULL AND
   (SELECT COUNT(*) FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.OrderManagement') AND index_id = 0) = 1
    ALTER TABLE dbo.OrderManagement REBUILD;

IF OBJECT_ID('dbo.OrderManagementHO') IS NOT NULL AND
   (SELECT COUNT(*) FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.OrderManagementHO') AND index_id = 0) = 1
    ALTER TABLE dbo.OrderManagementHO REBUILD;

IF OBJECT_ID('dbo.OrderPurchaseTrans') IS NOT NULL AND
   (SELECT COUNT(*) FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.OrderPurchaseTrans') AND index_id = 0) = 1
    ALTER TABLE dbo.OrderPurchaseTrans REBUILD;

PRINT '--- Step 2: rebuild all indexes on the Order Management table family ---';

DECLARE @tables TABLE (name sysname);
INSERT INTO @tables (name) VALUES
    ('OrderManagement'),
    ('OrderManagementBackup'),
    ('OrderManagementHO'),
    ('CentralOrderHeader'),
    ('CentralOrderDetail'),
    ('PurchaseTrans4Order'),
    ('OrderPurchaseTrans'),
    ('OrderSuppliers'),
    ('OrderHeaderDetails');

DECLARE @tbl sysname, @idx sysname, @sql nvarchar(max);

DECLARE tbl_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT t.name FROM @tables t WHERE OBJECT_ID('dbo.' + t.name) IS NOT NULL;

OPEN tbl_cursor;
FETCH NEXT FROM tbl_cursor INTO @tbl;
WHILE @@FETCH_STATUS = 0
BEGIN
    DECLARE idx_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT i.name FROM sys.indexes i
        WHERE i.object_id = OBJECT_ID('dbo.' + @tbl)
          AND i.type > 0 AND i.name IS NOT NULL;

    OPEN idx_cursor;
    FETCH NEXT FROM idx_cursor INTO @idx;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @sql = N'ALTER INDEX ' + QUOTENAME(@idx) + N' ON dbo.' + QUOTENAME(@tbl)
                 + N' REBUILD WITH (ONLINE = OFF, FILLFACTOR = 90);';
        PRINT @sql;
        EXEC sp_executesql @sql;
        FETCH NEXT FROM idx_cursor INTO @idx;
    END
    CLOSE idx_cursor;
    DEALLOCATE idx_cursor;

    -- Update statistics with a full scan after rebuild so the optimizer's
    -- row-estimates reflect the post-delete table sizes immediately.
    SET @sql = N'UPDATE STATISTICS dbo.' + QUOTENAME(@tbl) + N' WITH FULLSCAN;';
    PRINT @sql;
    EXEC sp_executesql @sql;

    FETCH NEXT FROM tbl_cursor INTO @tbl;
END
CLOSE tbl_cursor;
DEALLOCATE tbl_cursor;

PRINT '--- Step 3: shrink the OrderNMC data file ---';

DECLARE @dataFile sysname;
SELECT @dataFile = name FROM sys.database_files WHERE type_desc = 'ROWS';
SET @sql = N'DBCC SHRINKFILE (' + QUOTENAME(@dataFile) + N', 10);';
PRINT @sql;
EXEC sp_executesql @sql;

PRINT '--- Step 4: truncate the transaction log ---';

DECLARE @recoveryModel nvarchar(60);
SELECT @recoveryModel = recovery_model_desc FROM sys.databases WHERE name = 'OrderNMC';

IF @recoveryModel = 'SIMPLE'
BEGIN
    CHECKPOINT;
    DECLARE @logFile sysname;
    SELECT @logFile = name FROM sys.database_files WHERE type_desc = 'LOG';
    SET @sql = N'DBCC SHRINKFILE (' + QUOTENAME(@logFile) + N', 1);';
    PRINT @sql;
    EXEC sp_executesql @sql;
END
ELSE
BEGIN
    PRINT 'SKIPPED log shrink: OrderNMC recovery model is ' + @recoveryModel
        + ' -- back up the log first (BACKUP LOG OrderNMC TO ...), then DBCC SHRINKFILE on the log file, or this will not reclaim space.';
END

PRINT '--- Done ---';
