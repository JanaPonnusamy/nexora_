/* Procurement — D3c: rare-mover confirmation (discrete field, owner-approved 2026-10-21).
   Target database: NEXORA_PLATFORM (SQL Server).

   Decision on record (AUTONOMOUS_WORK_CONTROL.md / PHASE_2_CLAUDE_REVIEW.md D3/D3c):
   a discrete confirmation field, not a queue-based implicit-approval model.
   Confirmation is valid only for the current cycle — satisfied for free by
   storing it directly on procurement_order_items, since every new cycle/
   refresh mints new order_item rows (UNIQUE (refresh_id, product_id), see
   0004_procurement_order_items.sql). There is no cross-cycle row to misread
   a stale confirmation from; a new cycle's row starts with rare_confirmed = 0
   by construction. No separate (product_id, cycle_id) lookup table is needed.

   Adds (idempotent), mirroring the additive style of
   0007_order_item_review_fields.sql:
     rare_confirmed     — PM has explicitly confirmed this rare-mover line
     rare_confirmed_by  — user who confirmed (UNIQUEIDENTIFIER)
     rare_confirmed_at  — when confirmed

   NOT APPLIED. Written for review only, per the master prompt's migration
   restriction — do not run this against NEXORA_PLATFORM without explicit
   authorization.
*/

IF COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD rare_confirmed BIT NOT NULL DEFAULT 0;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed_by') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD rare_confirmed_by UNIQUEIDENTIFIER NULL;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'rare_confirmed_at') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD rare_confirmed_at DATETIME NULL;
GO
