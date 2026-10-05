-- Label Exporter grid: sync.Products (tenant_id, store_id, ProductCode) is
-- already indexed (IX_Products_Search, stock_availability module) but its
-- INCLUDE list is missing SaleUnit and SubLocation, both read by the grid
-- query (search_products) for every matching row. Without them, a filtered
-- search (e.g. one shelf letter) still pays a key/RID lookup per row against
-- the clustered index. This covering index removes that lookup.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Products') AND name = 'IX_Products_LabelGrid'
)
    CREATE NONCLUSTERED INDEX IX_Products_LabelGrid
        ON sync.Products (tenant_id, store_id, ProductCode)
        INCLUDE (ProductName, isactive, TotalStock, MRP, UnitDescription, SaleUnit, SubLocation);
GO
