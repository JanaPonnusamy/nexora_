/* Legacy Order -- order-calc query performance fix.

   The inline order query (sql/order_local.sql) reads ProductSaleInformation
   FOUR separate times -- SalesQuantity, MaxSalesQty, maxQtyInPeriod and the
   MaxSaleInfo window -- each one filtering the SAME way:

       StoreName = @storename
       SeriesTransID = 1
       TransactionValidity = 0
       Transactiondate >= @ODATA (last 90 days)
       GROUP BY ProductCode, SUM/MAX(Quantity)

   No existing index covers that predicate. The clustered PK is (ID, StoreName)
   and IX_ProductSaleInformation_Main leads with ProductCode (wrong order for a
   store-wide scan) and carries neither SeriesTransID nor Quantity. So each of
   the four passes scans this store's whole PSI slice (804k rows for NMC) and
   does key lookups for Quantity. Measured on NMC (read-only, warm cache):

       SalesQuantity   36.9s      MaxSalesQty     43.8s
       maxQtyInPeriod  27.6s      MaxSaleInfo     94.3s     -> full query ~100s

   With the covering index below (proven on a copy of NMC's PSI slice):

       SalesQuantity    4.1s (join+COUNT DISTINCT, not the scan)
       MaxSalesQty      0.07s     maxQtyInPeriod  0.08s     MaxSaleInfo 0.14s

   i.e. the PSI portion drops from ~200s of scan work to ~4s, and the whole
   order-calc query should fall from ~100s to single digits.

   Target database: OrderNMC (central, SQL Server 2014 Express).
   Idempotent. Run during a maintenance window: on Express there is no
   ONLINE=ON, so building this on the 2.7M-row ProductSaleInformation takes a
   table lock for the build (~tens of seconds) during which store syncs/orders
   block.
*/

------------------------------------------------------------------------------
-- 1. The covering index the order-calc query actually needs.
------------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = 'IX_PSI_Order_StoreSeriesValidityDate'
                AND object_id = OBJECT_ID('ProductSaleInformation'))
    CREATE INDEX IX_PSI_Order_StoreSeriesValidityDate
        ON ProductSaleInformation
            (StoreName, SeriesTransID, TransactionValidity, Transactiondate, ProductCode)
        INCLUDE (Quantity, DontConsiderInOrder, ID);
GO

------------------------------------------------------------------------------
-- 2. Redundant duplicate indexes found while profiling. Every one of these is
--    maintained on EVERY sync insert, so dropping them speeds the sync side up
--    and buys back the write cost of the new index above. Each pair/group below
--    is byte-for-byte duplicate key columns; we keep exactly one.
--
--    Review before running in case an external tool references a name by hand;
--    all are non-unique, non-PK helper indexes.
------------------------------------------------------------------------------

-- ProductSaleInformation: three IDENTICAL indexes on (Bnumber). Keep one.
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_PSI_Product_Sales' AND object_id=OBJECT_ID('ProductSaleInformation'))
    DROP INDEX IX_PSI_Product_Sales ON ProductSaleInformation;
GO
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_PSI_BillLookup' AND object_id=OBJECT_ID('ProductSaleInformation'))
    DROP INDEX IX_PSI_BillLookup ON ProductSaleInformation;
GO
-- (IX_PSI_Bill_Performance on (Bnumber) is kept.)

-- ProductSaleInformation: (StoreName, ID) exists twice. Keep the 0002 one.
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_ProductSaleInformation_Store_PK' AND object_id=OBJECT_ID('ProductSaleInformation'))
    DROP INDEX IX_ProductSaleInformation_Store_PK ON ProductSaleInformation;
GO

-- ProductTrans: (ProductCode, StoreName, MonthOfStatistics) equals the
-- clustered PK exactly, and (StoreName, ProductCode, MonthOfStatistics) exists
-- twice. Keep the clustered PK + the 0002 IX_ProductTrans_StoreName_ProductCode_Month.
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_ProductTrans_Product_Store_Month' AND object_id=OBJECT_ID('ProductTrans'))
    DROP INDEX IX_ProductTrans_Product_Store_Month ON ProductTrans;
GO
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_ProductTrans_Store_PK' AND object_id=OBJECT_ID('ProductTrans'))
    DROP INDEX IX_ProductTrans_Store_PK ON ProductTrans;
GO
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='idx_ProductTrans_Productcode_StoreName' AND object_id=OBJECT_ID('ProductTrans'))
    DROP INDEX idx_ProductTrans_Productcode_StoreName ON ProductTrans;  -- prefix of clustered PK
GO

-- Products: idx_products_sync (ProductCode, StoreName) is a prefix of the
-- clustered PK (ProductCode, StoreName). Redundant.
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='idx_products_sync' AND object_id=OBJECT_ID('Products'))
    DROP INDEX idx_products_sync ON Products;
GO
