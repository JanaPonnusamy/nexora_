/* Legacy Order -- Purchasetrans StoreName+Grnnumber lookup stall fix.

   Several hot paths (last-GRN checkpoint, qty_check_rows, order_process,
   supplier_whatsapp) filter Purchasetrans on (StoreName, Grnnumber), e.g.
   "SELECT TOP 1 Grndate FROM Purchasetrans WHERE StoreName = ? AND
   Grnnumber = ? ORDER BY Grndate DESC". No existing index leads with either
   column -- IX_PurchaseTrans_Product_Store_Date leads with ProductCode,
   IX_PurchaseTrans_Store_PK/StoreName_ID lead with StoreName but key on
   ID/ProductCode next, not Grnnumber -- so this forces a full scan of the
   whole table (1.4M+ rows) per call. Observed stuck 5-30s+ per call under
   concurrent load on the shared SQL Server Express instance (1GB
   buffer-pool cap), piling up as PAGEIOLATCH_SH waits across many sessions
   at once (2026-11-16).

   Target database: OrderNMC (central, SQL Server Express). Also apply to
   OrderSMS / OrderSuccess if Purchasetrans exists there.
   Idempotent -- safe to run more than once. Run during a maintenance
   window: building this index takes a table-level lock for the duration
   on Express edition (no ONLINE=ON).
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_PurchaseTrans_Store_Grn' AND object_id = OBJECT_ID('Purchasetrans')
)
    CREATE INDEX IX_PurchaseTrans_Store_Grn
        ON Purchasetrans (StoreName, Grnnumber)
        INCLUDE (Grndate, InvoiceSeries, SupplierCode, suppliername, ProductCode);
GO
