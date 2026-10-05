/* Stock Availability — Supplier Stock search performance fix.
   Target database: NEXORA_PLATFORM (SQL Server).

   The desktop Supplier Stock screen fans a single search out into 4-5 queries
   per store (product search, batches, purchases, sales, monthly movement,
   bill items). Several of the underlying synced tables (sync.Products,
   sync.Batches, sync.ProductSaleInformation, sync.SaleInformation,
   sync.SalesRep, sync.ProductTrans) carry no index beyond their clustered PK,
   forcing a full scan per store per query — the confirmed cause of the
   45-60s page load. sync.PurchaseTrans is already covered by
   backend/modules/procurement/sql/0014_purchase_trans_supplier_indexes.sql.

   Covering, read-only, nonclustered indexes matching the WHERE/JOIN columns
   in backend/modules/stock_availability/sql/stock_procedures.sql and
   pm_detail_procedures.sql. No schema change, no data change. Idempotent.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Products') AND name = 'IX_Products_Search'
)
    CREATE NONCLUSTERED INDEX IX_Products_Search
        ON sync.Products (tenant_id, store_id, ProductCode)
        INCLUDE (ProductName, isActive, TotalStock, MRP, UnitDescription);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Batches') AND name = 'IX_Batches_Product'
)
    CREATE NONCLUSTERED INDEX IX_Batches_Product
        ON sync.Batches (tenant_id, store_id, ProductCode)
        INCLUDE (BatchCode, Stock, MRP, ExpiryDate, GrnDate, PurchasePrice, LastSaleDate);
GO
/* NOTE: LastSaleDate added to the INCLUDE list above (fresh installs get it
   here). Existing databases already carrying this index without LastSaleDate
   are upgraded in place by 0003_batches_lastsaledate_index.sql. */

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.ProductSaleInformation') AND name = 'IX_ProductSaleInformation_Product'
)
    CREATE NONCLUSTERED INDEX IX_ProductSaleInformation_Product
        ON sync.ProductSaleInformation (tenant_id, store_id, ProductCode)
        INCLUDE (TransactionDate, Bnumber, BillNumber, SeriesName, Quantity, MRP,
                 DiscountPercentage, TransactionValidity, Transactionamount);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.SaleInformation') AND name = 'IX_SaleInformation_Bill'
)
    CREATE NONCLUSTERED INDEX IX_SaleInformation_Bill
        ON sync.SaleInformation (tenant_id, store_id, BNumber)
        INCLUDE (BillDate, CustomerName, DeliverySalesRep, BillNumber);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.SalesRep') AND name = 'IX_SalesRep_Code'
)
    CREATE NONCLUSTERED INDEX IX_SalesRep_Code
        ON sync.SalesRep (tenant_id, store_id, Salesmancode)
        INCLUDE (Salesmanname);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.ProductTrans') AND name = 'IX_ProductTrans_Product'
)
    CREATE NONCLUSTERED INDEX IX_ProductTrans_Product
        ON sync.ProductTrans (tenant_id, store_id, ProductCode)
        INCLUDE (MonthOfStatistics, LastBillDate, LastGrnDate, PurchaseQuantity,
                 SaleQuantity, TransferInQuantity, TransferOutQuantity,
                 AdjustmentQuantity, StockInHand);
GO
