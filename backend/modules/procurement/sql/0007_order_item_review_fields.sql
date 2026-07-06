/* Procurement — Sprint 2 (Purchase Manager): Working Order Item review fields.
   Target database: NEXORA_PLATFORM (SQL Server).

   The Purchase Manager reviews Working Order Items: adjusts Final Quantity
   (with the option to restore the engine's Suggested Quantity), or Skips a
   product with a reason. Adds the tracking columns for that workflow. The
   workflow status itself continues to live in the existing item_status column
   (draft | review | assigned | partial | skipped).

   Adds (idempotent):
     suggested_qty  — the engine's original suggestion, preserved for "restore"
     skip_reason    — reason captured when a product is skipped
     reviewed_by    — user who last reviewed the item (UNIQUEIDENTIFIER)
     reviewed_at    — when the item was last reviewed
*/

IF COL_LENGTH('procurement.procurement_order_items', 'suggested_qty') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD suggested_qty DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'skip_reason') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD skip_reason VARCHAR(300) NULL;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'reviewed_by') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD reviewed_by UNIQUEIDENTIFIER NULL;
GO
IF COL_LENGTH('procurement.procurement_order_items', 'reviewed_at') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD reviewed_at DATETIME NULL;
GO
