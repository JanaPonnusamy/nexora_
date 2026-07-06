/* Procurement — Sprint 3 (GRN, Pending, Next Refresh): reconciliation fields.
   Target database: NEXORA_PLATFORM (SQL Server).

   Completes the workflow after Export: GRN completion, assignment
   reconciliation, pending management and cycle closing. No new tables (Pending
   stays as remaining_qty; Export stays on the assignment). Idempotent.

   Refresh   : last_grn_number, grn_completed_at  (Module 1 GRN completion)
   Assignment: remaining_qty (assigned - received), last_grn_sync_at (Module 2)
   Order item: received_qty (SUM of assignment receipts), is_manual (manual
               procurement line), pending_status (pending review outcome)
*/

/* --- Refresh: GRN completion markers ------------------------------------ */
IF COL_LENGTH('procurement.procurement_refreshes', 'last_grn_number') IS NULL
    ALTER TABLE procurement.procurement_refreshes ADD last_grn_number VARCHAR(50) NULL;
GO
IF COL_LENGTH('procurement.procurement_refreshes', 'grn_completed_at') IS NULL
    ALTER TABLE procurement.procurement_refreshes ADD grn_completed_at DATETIME NULL;
GO

/* --- Assignment: per-line reconciliation -------------------------------- */
IF COL_LENGTH('procurement.procurement_order_item_assignments', 'remaining_qty') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments ADD remaining_qty DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_order_item_assignments', 'last_grn_sync_at') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments ADD last_grn_sync_at DATETIME NULL;
GO

/* --- Order item: receipts, manual lines, pending outcome ---------------- */
IF COL_LENGTH('procurement.procurement_order_items', 'received_qty') IS NULL
    ALTER TABLE procurement.procurement_order_items ADD received_qty DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'is_manual') IS NULL
    ALTER TABLE procurement.procurement_order_items ADD is_manual BIT NOT NULL DEFAULT 0;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'pending_status') IS NULL
    ALTER TABLE procurement.procurement_order_items ADD pending_status VARCHAR(20) NULL;
GO
