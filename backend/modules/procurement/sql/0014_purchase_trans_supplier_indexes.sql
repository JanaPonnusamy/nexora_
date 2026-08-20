/* Procurement — Supplier Purchasing / Supplier Live Stock performance fix.
   Target database: NEXORA_PLATFORM (SQL Server).

   sync.PurchaseTrans (a synced legacy table, 1M+ rows for a single store in
   production) carries NO index beyond its clustered PK (store_id, ID) — every
   supplier_repository query that filters or joins on ProductCode/SupplierCode
   was forcing a full clustered-index scan. This is the confirmed root cause of
   the 20-30s "select a supplier" delay in Supplier Purchasing (measured live:
   24.98s for products_for_supplier before this fix).

   Two covering, read-only indexes — no schema change, no data change:
     - IX_PurchaseTrans_Supplier: seeks by (tenant_id, store_id, SupplierCode),
       covers ProductCode — used by products_for_supplier's supplier filter.
     - IX_PurchaseTrans_Product: seeks by (tenant_id, store_id, ProductCode),
       covers the columns top_suppliers_bulk aggregates — used by the
       refresh-wide supplier recommendation join.

   These only help once the query predicates stop wrapping the indexed columns
   in CAST(...) (a CAST prevents an index seek regardless of what index
   exists) — see the matching supplier_repository.py changes in this same
   change set.

   Idempotent.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.PurchaseTrans') AND name = 'IX_PurchaseTrans_Supplier'
)
    CREATE NONCLUSTERED INDEX IX_PurchaseTrans_Supplier
        ON sync.PurchaseTrans (tenant_id, store_id, SupplierCode)
        INCLUDE (ProductCode);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.PurchaseTrans') AND name = 'IX_PurchaseTrans_Product'
)
    CREATE NONCLUSTERED INDEX IX_PurchaseTrans_Product
        ON sync.PurchaseTrans (tenant_id, store_id, ProductCode)
        INCLUDE (SupplierCode, GRNDate, GRNNumber, PurchasePrice);
GO
