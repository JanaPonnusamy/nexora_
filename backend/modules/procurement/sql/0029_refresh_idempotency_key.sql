/* Procurement — D5: refresh retry idempotency (owner-approved 2026-10-21:
   client-supplied idempotency key, not a parameter-dedup window).
   Target database: NEXORA_PLATFORM (SQL Server).

   Adds (idempotent), mirroring 0007_order_item_review_fields.sql's style:
     idempotency_key — optional, caller-supplied opaque string. A retried
       create-refresh call with the same (tenant_id, cycle_id, idempotency_key)
       returns the existing Refresh instead of minting a new one.

   A unique filtered index (NULLs excluded) lets many Refreshes have no key
   (existing/legacy callers) while still enforcing "one Refresh per key per
   cycle" for callers that do supply one — this is the actual source of
   truth for the dedup check, not an application-level SELECT-then-INSERT,
   so it is race-safe under real concurrent retries (duplicate key insert
   fails with a constraint violation the service layer catches and treats as
   "someone else already created it, read theirs").

   NOT APPLIED. Written for review only.
*/

IF COL_LENGTH('procurement.procurement_refreshes', 'idempotency_key') IS NULL
    ALTER TABLE procurement.procurement_refreshes
        ADD idempotency_key VARCHAR(200) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UX_procurement_refreshes_idempotency_key'
      AND object_id = OBJECT_ID('procurement.procurement_refreshes')
)
    CREATE UNIQUE INDEX UX_procurement_refreshes_idempotency_key
        ON procurement.procurement_refreshes (tenant_id, cycle_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
GO
