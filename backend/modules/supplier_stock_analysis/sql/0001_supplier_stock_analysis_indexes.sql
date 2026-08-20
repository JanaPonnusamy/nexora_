/* Supplier Stock Analysis performance indexes.
   Target database: NEXORA_PLATFORM (SQL Server).

   The desktop Supplier Stock Analysis screen opens one supplier row at a time,
   then fans out into:
   - procurement.supplier_stock lookup by supplier_stock_id / supplier scope
   - sync.SupplierProductMatch resolution by tenant+store+supplier+product
   - sync.Products lookup by tenant+store+product_code

   The screen already stores the resolved ProductCode on
   procurement.supplier_stock.product_code; this script makes the remaining
   lookups cheap and covering. No data change. Idempotent.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('procurement.supplier_stock') AND name = 'IX_supplier_stock_analysis_row_open'
)
    CREATE NONCLUSTERED INDEX IX_supplier_stock_analysis_row_open
        ON procurement.supplier_stock (supplier_stock_id, tenant_id, is_active)
        INCLUDE (store_id, supplier_code, supplier_product_code, supplier_product_name,
                 product_code, available_stock, ptr, mrp, discount, packing, free,
                 minimum_qty, scheme);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('procurement.supplier_stock') AND name = 'IX_supplier_stock_analysis_scope'
)
    CREATE NONCLUSTERED INDEX IX_supplier_stock_analysis_scope
        ON procurement.supplier_stock (tenant_id, store_id, supplier_code, is_active, supplier_product_code)
        INCLUDE (supplier_stock_id, supplier_product_name, product_code, available_stock,
                 ptr, mrp, discount, packing, free, minimum_qty, scheme, imported_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.SupplierProductMatch') AND name = 'IX_SupplierProductMatch_SupplierLookup'
)
    CREATE NONCLUSTERED INDEX IX_SupplierProductMatch_SupplierLookup
        ON sync.SupplierProductMatch (tenant_id, store_id, SupplierCode, SupplierProductCode, IsActive)
        INCLUDE (ProductCode, SupplierProductName, UserName, LastModifiedDate);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Products') AND name = 'IX_Products_TenantStoreCode'
)
    CREATE NONCLUSTERED INDEX IX_Products_TenantStoreCode
        ON sync.Products (tenant_id, store_id, ProductCode)
        INCLUDE (ProductName, IsActive, TotalStock, SaleUnit, UnitDescription, MRP, PurchasePrice);
GO
