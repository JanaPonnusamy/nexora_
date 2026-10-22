/* Legacy Order -- Qty Check sidebar (Purchase/GRN + Bill/Sales panels) perf.

   Every time the operator selects a row in Order Workspace, the sidebar
   fires two per-product lookups:

     qty_check_purchase_details (repository.py):
       SELECT TOP 10 ... FROM PurchaseTrans pt
       WHERE pt.ProductCode = ? AND pt.StoreName = ?
       ORDER BY pt.GRNDate DESC

     qty_check_sales_details (repository.py):
       SELECT TOP 10 ... FROM ProductSaleInformation PS
       INNER JOIN SaleInformation s ON PS.BillNumber = s.BillNumber
                                    AND PS.TransactionDate = s.BillDate
       INNER JOIN SalesRep sr ON s.DeliverySalesRep = sr.Salesmancode
       WHERE PS.ProductCode = ? AND PS.TransactionValidity = 0
         AND PS.StoreName = ? AND s.StoreName = ? AND sr.StoreName = ?

   Neither predicate is covered by an existing index:
     - 0002's IX_PurchaseTrans_StoreName_ID leads with StoreName, not
       ProductCode -- a per-product GRN lookup still scans the store's whole
       PurchaseTrans slice.
     - 0005's IX_PSI_Order_StoreSeriesValidityDate leads with StoreName too
       (built for the order-calc query's store-wide scan, not a per-product
       point lookup), and doesn't include TransactionDate/BillNumber for the
       SaleInformation join.

   This fires on every single row click in the grid (not once per screen
   load), so the per-row sidebar lag compounds directly into "switching
   screens/rows feels slow" -- this is the other half of that symptom
   alongside the Order-Workspace-stays-mounted fix (see AppShell).

   Target database: OrderNMC (central, SQL Server 2014 Express).
   Idempotent -- safe to run more than once. Run during a maintenance
   window: Express has no ONLINE=ON, so building these takes a table lock
   for the duration.
*/

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = 'IX_PurchaseTrans_ProductCode_Store_GRNDate'
                AND object_id = OBJECT_ID('PurchaseTrans'))
    CREATE INDEX IX_PurchaseTrans_ProductCode_Store_GRNDate
        ON PurchaseTrans (ProductCode, StoreName, GRNDate DESC)
        INCLUDE (StockReceived, FreeQty, ProductDiscPercent, ItemCost, PurchasePrice, MRP, InvoiceSeries, SupplierCode);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
              WHERE name = 'IX_PSI_ProductCode_Validity_Store'
                AND object_id = OBJECT_ID('ProductSaleInformation'))
    CREATE INDEX IX_PSI_ProductCode_Validity_Store
        ON ProductSaleInformation (ProductCode, TransactionValidity, StoreName)
        INCLUDE (BillNumber, TransactionDate, Bnumber, DiscountPercentage, Seriesname, mrp, purchaseprice, Quantity, Lastadjustmentdate);
GO
