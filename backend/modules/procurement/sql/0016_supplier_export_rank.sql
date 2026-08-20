/* Procurement — Supplier Export Rank (manual priority order for Auto Assign's
   Rank mode). Target database: NEXORA_PLATFORM (SQL Server), table:
   sync.Suppliers.

   export_rank (int, default NULL = unranked): a buyer-set priority — rank 1
   gets first crack at every eligible product it can supply, rank 2 gets
   whatever's left, and so on. Unranked suppliers sort after every ranked one
   and are never picked in Rank mode (Cost mode is unaffected — it keeps using
   the existing weighted score, not this column).

   Same convention as auto_assign/min_products (migration 0015): directly on
   sync.Suppliers, no separate procurement.* overlay table (owner-directed).
   See that migration's own comment for the sync-job-overwrite caveat, which
   applies here too.

   Idempotent.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('sync.Suppliers') AND name = 'export_rank'
)
    ALTER TABLE sync.Suppliers ADD export_rank INT NULL;
GO
