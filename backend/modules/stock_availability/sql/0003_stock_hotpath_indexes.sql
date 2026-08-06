/* Stock Availability hot-path indexes.
   Target database: NEXORA_PLATFORM (SQL Server).

   Live profiling on 2026-07-23 showed the main slow procedures are:
   - stock.usp_ProductSearch
   - stock.usp_ProductCore
   - stock.usp_BillItems

   Existing indexes cover several product-code lookups, but two hot paths were
   still under-indexed:
   1) prefix ProductName search in sync.Products
   2) TOP(1) latest ProductTrans row per (tenant, store, product)
   3) BillItems lookup by BillNumber + TransactionDate in sync.ProductSaleInformation
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Products') AND name = 'IX_Products_TenantProductName'
)
    CREATE NONCLUSTERED INDEX IX_Products_TenantProductName
        ON sync.Products (tenant_id, ProductName, store_id)
        INCLUDE (ProductCode, UnitDescription, TotalStock, MRP, IsActive);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.ProductTrans') AND name = 'IX_ProductTrans_LatestStock'
)
    CREATE NONCLUSTERED INDEX IX_ProductTrans_LatestStock
        ON sync.ProductTrans (tenant_id, store_id, ProductCode, MonthOfStatistics DESC)
        INCLUDE (StockInHand, LastBillDate, LastGrnDate, PurchaseQuantity,
                 SaleQuantity, TransferInQuantity, TransferOutQuantity,
                 AdjustmentQuantity);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.ProductSaleInformation') AND name = 'IX_ProductSaleInformation_BillLookup'
)
    CREATE NONCLUSTERED INDEX IX_ProductSaleInformation_BillLookup
        ON sync.ProductSaleInformation (tenant_id, store_id, BillNumber, TransactionDate)
        INCLUDE (SeriesName, ProductCode, Quantity, MRP, DiscountPercentage,
                 Transactionamount, TransactionValidity);
GO
