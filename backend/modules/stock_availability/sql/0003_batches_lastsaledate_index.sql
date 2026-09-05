/* Label Exporter (and any LastSaleDate aggregation) performance fix.
   Target database: NEXORA_PLATFORM (SQL Server).

   IX_Batches_Product (see 0002_search_performance_indexes.sql) covers
   GrnDate/Stock but NOT LastSaleDate. The Label Exporter product search
   aggregates MAX(b.LastSaleDate) per product (LSD column + the stock rule's
   "sold within 90 days" test). Because LastSaleDate is uncovered, that
   aggregation cannot be served from the narrow nonclustered index and falls
   back to reading the wide 541K-row clustered index. Measured impact:

       aggregation WITHOUT LastSaleDate:  N=1 0.16s  N=40 concurrent 166/s
       aggregation WITH    LastSaleDate:  N=1 0.58s  N=40 concurrent 6.7/s

   Under concurrency (multiple clients + the constant store-agent sync traffic
   hitting the same DB) the uncovered reads serialize backend throughput to
   ~6 req/s. A modest backlog then exceeds the client's 45s timeout — the
   "Request timed out after 45s" the Label Exporter grid shows.

   Fix: add LastSaleDate to the INCLUDE list so the aggregation is fully
   index-covered. Additive INCLUDE only (no key change, no schema/data change).
   DROP_EXISTING rebuilds the existing index in place. Idempotent: re-running
   is a no-op once LastSaleDate is present.
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID('sync.Batches') AND i.name = 'IX_Batches_Product'
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
