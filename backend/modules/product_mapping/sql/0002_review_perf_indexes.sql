/* Product Mapping — Manual Review performance indexes (Phase 2).
   Target database: NEXORA_PLATFORM (SQL Server).

   Profiled against a live 1.1M-row product_mapping table (473K PENDING) using
   SET STATISTICS XML. The existing IX_product_mapping_tenant_status index
   (tenant_id, is_deleted, status) does not lead with source_store_id /
   target_store_id, so every store-pair-scoped Manual Review query (list,
   progress counters, bulk approve/reject) fell back to a full index scan +
   explicit Sort for ORDER BY confidence DESC, plus a Key Lookup per row for
   SELECT *. Cold-cache page-1 load measured 88,272 ms before this migration.

   Idempotent: safe to run more than once.
*/

USE NEXORA_PLATFORM;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* ---------------------------------------------------------------------------
   IX_product_mapping_review_queue — the Manual Review workhorse index.
   Leads with the four equality predicates every review query filters on
   (tenant/source store/target store/status), then the ORDER BY columns
   (confidence DESC, mapping_id as a stable keyset tie-breaker) so the engine
   can seek + return rows in order with NO explicit Sort operator. Filtered on
   is_deleted = 0 to match every query (and keep the index small — soft-deleted
   rows never need to be found this way).
--------------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_product_mapping_review_queue'
      AND object_id = OBJECT_ID('dbo.product_mapping')
)
BEGIN
    CREATE INDEX IX_product_mapping_review_queue
        ON dbo.product_mapping (tenant_id, source_store_id, target_store_id, status, confidence DESC, mapping_id)
        WHERE is_deleted = 0;
END
GO

/* ---------------------------------------------------------------------------
   IX_product_mapping_updated — supports the "approved today" counter
   (status = 'APPROVED' AND updated_at >= today) without scanning every
   APPROVED row for the store pair ever recorded.
--------------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_product_mapping_updated'
      AND object_id = OBJECT_ID('dbo.product_mapping')
)
BEGIN
    CREATE INDEX IX_product_mapping_updated
        ON dbo.product_mapping (tenant_id, source_store_id, target_store_id, status, updated_at)
        WHERE is_deleted = 0;
END
GO

/* ---------------------------------------------------------------------------
   IX_product_mapping_source_code — supports the Manual Review search box's
   code-prefix branch (source_product_code LIKE ? + '%'). The name branch
   (LIKE '%term%') is a leading-wildcard scan by nature and cannot be indexed
   without full-text search, which is out of scope for this pass.
--------------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_product_mapping_source_code'
      AND object_id = OBJECT_ID('dbo.product_mapping')
)
BEGIN
    CREATE INDEX IX_product_mapping_source_code
        ON dbo.product_mapping (tenant_id, source_store_id, target_store_id, source_product_code)
        WHERE is_deleted = 0;
END
GO
