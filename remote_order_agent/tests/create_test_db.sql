/* Throw-away test database: SCHEMA ONLY copy of the OrderNMC tables the integration touches.
   No rows are copied from live. Dropped by drop_test_db.sql after testing. */
:on error exit
SET NOCOUNT ON;
USE master;
IF DB_ID('OrderNMC_IntTest') IS NOT NULL BEGIN ALTER DATABASE OrderNMC_IntTest SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE OrderNMC_IntTest; END;
CREATE DATABASE OrderNMC_IntTest COLLATE Latin1_General_CI_AI;
ALTER DATABASE OrderNMC_IntTest SET RECOVERY SIMPLE;
GO
USE OrderNMC_IntTest;
-- column definitions (types, nullability, collation) copied from live, zero rows
SELECT TOP 0 * INTO dbo.OrderManagement       FROM OrderNMC.dbo.OrderManagement;
SELECT TOP 0 * INTO dbo.OrderManagementBackup FROM OrderNMC.dbo.OrderManagementBackup;
SELECT TOP 0 * INTO dbo.OrderHeaderDetails    FROM OrderNMC.dbo.OrderHeaderDetails;
SELECT TOP 0 * INTO dbo.Products              FROM OrderNMC.dbo.Products;
SELECT TOP 0 * INTO dbo.ProductSaleInformation FROM OrderNMC.dbo.ProductSaleInformation;
SELECT TOP 0 * INTO dbo.SaleInformation       FROM OrderNMC.dbo.SaleInformation;
SELECT TOP 0 * INTO dbo.ProductTrans          FROM OrderNMC.dbo.ProductTrans;
SELECT TOP 0 * INTO dbo.PurchaseTrans         FROM OrderNMC.dbo.PurchaseTrans;
SELECT TOP 0 * INTO dbo.SalesRep              FROM OrderNMC.dbo.SalesRep;
SELECT TOP 0 * INTO dbo.Batches               FROM OrderNMC.dbo.Batches;
SELECT TOP 0 * INTO dbo.SupplierProductMatch  FROM OrderNMC.dbo.SupplierProductMatch;
SELECT TOP 0 * INTO dbo.OrderSuppliers        FROM OrderNMC.dbo.OrderSuppliers;
SELECT TOP 0 * INTO dbo.stores                FROM OrderNMC.dbo.stores;
GO
-- keys and defaults exactly as live
ALTER TABLE dbo.OrderManagement ADD CONSTRAINT DF_t_OM_Qtycheck DEFAULT ((0)) FOR Qtycheck;
ALTER TABLE dbo.OrderManagementBackup ADD CONSTRAINT PK_OrderManagementBackup PRIMARY KEY (StoreName, OrderId, ProductCode);
ALTER TABLE dbo.OrderManagementBackup ADD CONSTRAINT DF_t_OMB_Tdate DEFAULT (getdate()) FOR Transactiondate;
ALTER TABLE dbo.OrderManagementBackup ADD CONSTRAINT DF_t_OMB_Qc DEFAULT ((10)) FOR Qtycheck;
ALTER TABLE dbo.OrderHeaderDetails ADD CONSTRAINT PK_OHD PRIMARY KEY (OrderId);
ALTER TABLE dbo.Products ADD CONSTRAINT PK_Products PRIMARY KEY (ProductCode, StoreName);
ALTER TABLE dbo.ProductSaleInformation ADD CONSTRAINT PK_PSI PRIMARY KEY (ID, StoreName);
ALTER TABLE dbo.SaleInformation ADD CONSTRAINT PK_SI PRIMARY KEY (BillDate, BNumber, StoreName);
ALTER TABLE dbo.ProductTrans ADD CONSTRAINT PK_PT PRIMARY KEY (ProductCode, StoreName, MonthOfStatistics);
ALTER TABLE dbo.PurchaseTrans ADD CONSTRAINT PK_PurT PRIMARY KEY (ID, ProductCode, StoreName);
ALTER TABLE dbo.SalesRep ADD CONSTRAINT PK_SR PRIMARY KEY (SalesmanCode, StoreName);
ALTER TABLE dbo.Batches ADD CONSTRAINT PK_Batches PRIMARY KEY (ProductCode, BatchCode, StoreName);
ALTER TABLE dbo.SupplierProductMatch ADD CONSTRAINT PK_SPM PRIMARY KEY (SupplierCode, SupplierProductCode, StoreName);
ALTER TABLE dbo.OrderSuppliers ADD CONSTRAINT PK_OS PRIMARY KEY (StoreName, suppliercode);
ALTER TABLE dbo.stores ADD CONSTRAINT PK_stores PRIMARY KEY (storecode);
GO
PRINT 'OrderNMC_IntTest created (schema only).';
