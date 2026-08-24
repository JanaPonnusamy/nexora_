/* Product Mapping — reverse (target-side) lookup index for Supplier Stock
   Analysis. Target database: NEXORA_PLATFORM (SQL Server).

   Supplier Stock Analysis' "supplier-products" query computes, per supplier
   stock row, how many OTHER stores the mapped product resolves to. It walks the
   mapping graph in BOTH directions:

     forward:  source_store_id = X  AND source_product_code = code   (served by
               the existing UX_product_mapping_source_target unique index)
     reverse:  target_store_id = X  AND target_product_code = code

   The reverse branch had NO supporting index (every existing index leads with
   source_store_id / status), so it fell back to a full scan of the 1.1M-row
   product_mapping table. Run once per candidate row inside an OUTER APPLY, a
   cold-cache "supplier-products" request measured 70+ seconds and tripped the
   desktop client's 45s timeout ("Request timed out after 45s", 0 rows shown).

   This index mirrors IX_product_mapping_source_code for the target direction so
   the reverse branch seeks instead of scans (measured sub-second after this
   migration). source_store_id / status are carried as INCLUDE columns so the
   reverse lookup is covering (no key lookup back to the heap/clustered index).

   Idempotent: safe to run more than once.
*/

USE NEXORA_PLATFORM;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_product_mapping_target_code'
      AND object_id = OBJECT_ID('dbo.product_mapping')
)
BEGIN
    CREATE INDEX IX_product_mapping_target_code
        ON dbo.product_mapping (tenant_id, target_store_id, target_product_code)
        INCLUDE (source_store_id, status)
        WHERE is_deleted = 0;
END
GO
