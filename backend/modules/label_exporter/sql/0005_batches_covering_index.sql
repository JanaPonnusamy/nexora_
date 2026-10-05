/* Label Exporter grid performance — guarantee the Batches covering index.
   Target database: NEXORA_PLATFORM (SQL Server).

   The product-search query aggregates sync.Batches per product
   (MAX GrnDate = LPD, MAX LastSaleDate = LSD, SUM Stock) for EVERY matched
   row. On a store whose Batches table is large (hundreds of thousands of rows)
   this aggregation, if it cannot be served from a narrow covering index, falls
   back to reading the wide clustered index — which under the constant
   store-agent sync traffic serializes to a few requests/second and makes a
   single-letter search (e.g. letter "A" on NMS) take 30s+ / time out.

   The identical index is also shipped by the stock_availability module
   (0002/0003), but the Label Exporter module does not run those files, so on a
   DB provisioned/synced only through the label path the index can be missing or
   not yet covering LastSaleDate. This migration makes the label module
   self-sufficient. Idempotent + additive (no key change, no schema/data
   change): creates the index if absent, or rebuilds it in place (DROP_EXISTING)
   only to add LastSaleDate to an older index that lacks it. Re-running is a
   no-op once the index is present and covers LastSaleDate. */

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Batches') AND name = 'IX_Batches_Product'
)
    CREATE NONCLUSTERED INDEX IX_Batches_Product
        ON sync.Batches (tenant_id, store_id, ProductCode)
        INCLUDE (BatchCode, Stock, MRP, ExpiryDate, GrnDate, PurchasePrice, LastSaleDate);
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('sync.Batches') AND name = 'IX_Batches_Product'
)
AND NOT EXISTS (
    SELECT 1
    FROM sys.index_columns ic
    JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE ic.object_id = OBJECT_ID('sync.Batches')
      AND ic.index_id = (SELECT index_id FROM sys.indexes WHERE object_id = OBJECT_ID('sync.Batches') AND name = 'IX_Batches_Product')
      AND ic.is_included_column = 1
      AND c.name = 'LastSaleDate'
)
    CREATE NONCLUSTERED INDEX IX_Batches_Product
        ON sync.Batches (tenant_id, store_id, ProductCode)
        INCLUDE (BatchCode, Stock, MRP, ExpiryDate, GrnDate, PurchasePrice, LastSaleDate)
        WITH (DROP_EXISTING = ON);
GO
