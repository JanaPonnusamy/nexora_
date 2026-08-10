/* Legacy Order -- deadlock/perf fix.

   Every table below is a SHARED central table in OrderNMC: every store's
   sync/order-process run reads and writes it filtered by StoreName (or the
   MERGE key that includes StoreName), but none of them had a supporting
   index. Without one, a `WHERE StoreName = ?` or a MERGE ... ON match scans
   the WHOLE table (all stores' rows, not just this one's) and takes locks
   across it, so two stores running at once overlap and SQL Server kills one
   as a deadlock victim (1205, SQLSTATE 40001). Indexing the filter/merge
   columns turns those scans into seeks scoped to just that store's rows,
   which removes the lock overlap and -- since these are also the biggest
   tables in the database -- is the main cost of the slow runs.

   Target database: OrderNMC (central, SQL Server 2014 Express).
   Idempotent -- safe to run more than once. Run during a maintenance window:
   building these indexes takes a table-level lock for the duration on
   Express edition (no ONLINE=ON), and the "huge" tables can take a while.
*/

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OrderManagement_StoreName_WantedType' AND object_id = OBJECT_ID('OrderManagement'))
    CREATE INDEX IX_OrderManagement_StoreName_WantedType ON OrderManagement (StoreName, WantedType);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OrderHeaderDetails_StoreName_OrderId' AND object_id = OBJECT_ID('OrderHeaderDetails'))
    CREATE INDEX IX_OrderHeaderDetails_StoreName_OrderId ON OrderHeaderDetails (StoreName, OrderId DESC);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ProductSaleInformation_StoreName_ID' AND object_id = OBJECT_ID('ProductSaleInformation'))
    CREATE INDEX IX_ProductSaleInformation_StoreName_ID ON ProductSaleInformation (StoreName, ID);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_PurchaseTrans_StoreName_ID' AND object_id = OBJECT_ID('PurchaseTrans'))
    CREATE INDEX IX_PurchaseTrans_StoreName_ID ON PurchaseTrans (StoreName, ID);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SaleInformation_StoreName_BillNumber_BillDate' AND object_id = OBJECT_ID('SaleInformation'))
    CREATE INDEX IX_SaleInformation_StoreName_BillNumber_BillDate ON SaleInformation (StoreName, BillNumber, BillDate);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ProductTrans_StoreName_ProductCode_Month' AND object_id = OBJECT_ID('ProductTrans'))
    CREATE INDEX IX_ProductTrans_StoreName_ProductCode_Month ON ProductTrans (StoreName, ProductCode, MonthOfStatistics);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OrderSuppliers_StoreName_SupplierCode' AND object_id = OBJECT_ID('OrderSuppliers'))
    CREATE INDEX IX_OrderSuppliers_StoreName_SupplierCode ON OrderSuppliers (StoreName, suppliercode);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SalesRep_StoreName_SalesmanCode' AND object_id = OBJECT_ID('SalesRep'))
    CREATE INDEX IX_SalesRep_StoreName_SalesmanCode ON SalesRep (StoreName, Salesmancode);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Batches_StoreName_ProductCode_BatchCode' AND object_id = OBJECT_ID('Batches'))
    CREATE INDEX IX_Batches_StoreName_ProductCode_BatchCode ON Batches (StoreName, ProductCode, BatchCode);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SupplierProductMatch_StoreName_Supplier_ProductCode' AND object_id = OBJECT_ID('SupplierProductMatch'))
    CREATE INDEX IX_SupplierProductMatch_StoreName_Supplier_ProductCode ON SupplierProductMatch (StoreName, suppliercode, supplierproductcode);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Products_StoreName_ProductCode' AND object_id = OBJECT_ID('Products'))
    CREATE INDEX IX_Products_StoreName_ProductCode ON Products (StoreName, ProductCode);
GO
