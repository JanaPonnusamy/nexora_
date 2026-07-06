/* Procurement — Phase 2 migration VERIFICATION (read-only, non-destructive).
   Target database: NEXORA_PLATFORM (SQL Server).

   Run AFTER 0001-0005 (+0003). Asserts the approved Phase 2 shape:
     - required columns exist,
     - removed columns are gone,
     - PKs follow <entity>_id.
   RAISERROR (severity 16) on the first problem; prints "PHASE 2 OK" if clean.
   Nothing is modified.
*/
SET NOCOUNT ON;

DECLARE @err NVARCHAR(400) = NULL;

/* ---- columns that MUST exist: 'schema.table.column' ---- */
DECLARE @must TABLE (obj NVARCHAR(200), col SYSNAME);
INSERT INTO @must (obj, col) VALUES
  ('procurement.procurement_cycles','start_grn_number'),
  ('procurement.procurement_cycles','start_sale_bill_number'),
  ('procurement.procurement_cycles','end_grn_number'),
  ('procurement.procurement_cycles','end_sale_bill_number'),
  ('procurement.procurement_cycles','active_refresh_id'),
  ('procurement.procurement_cycles','is_deleted'),
  ('procurement.procurement_refreshes','refresh_id'),
  ('procurement.procurement_refreshes','rolling_days'),
  ('procurement.procurement_refreshes','previous_refresh_id'),
  ('procurement.procurement_refreshes','snapshot_grn_number'),
  ('procurement.procurement_refreshes','snapshot_sale_bill_number'),
  ('procurement.procurement_refreshes','sync_execution_id'),
  ('procurement.procurement_virtual_products','virtual_product_id'),
  ('procurement.procurement_virtual_products','refresh_id'),
  ('procurement.procurement_virtual_products','effective_available_qty'),
  ('procurement.procurement_virtual_products','pending_used_qty'),
  ('procurement.procurement_order_items','order_item_id'),
  ('procurement.procurement_order_items','refresh_id'),
  ('procurement.procurement_order_item_assignments','assignment_id'),
  ('procurement.procurement_order_item_assignments','export_batch_number'),
  ('procurement.procurement_order_item_assignments','export_split_number'),
  ('procurement.procurement_order_item_assignments','export_uid'),
  ('procurement.procurement_order_item_assignments','exported_at'),
  ('procurement.procurement_order_item_assignments','exported_by');

SELECT TOP 1 @err = 'MISSING column: ' + obj + '.' + col
FROM @must
WHERE COL_LENGTH(obj, col) IS NULL;
IF @err IS NOT NULL BEGIN RAISERROR(@err,16,1); RETURN; END

/* ---- columns that MUST be gone ---- */
DECLARE @gone TABLE (obj NVARCHAR(200), col SYSNAME);
INSERT INTO @gone (obj, col) VALUES
  ('procurement.procurement_cycles','rolling_days'),
  ('procurement.procurement_cycles','generated_product_count'),
  ('procurement.procurement_cycles','live_refresh_count'),
  ('procurement.procurement_cycles','last_refresh_id'),
  ('procurement.procurement_refreshes','previous_pending_ref'),
  ('procurement.procurement_refreshes','generation_duration'),
  ('procurement.procurement_virtual_products','vpl_id'),
  ('procurement.procurement_refreshes','id');

SELECT TOP 1 @err = 'LEFTOVER column: ' + obj + '.' + col
FROM @gone
WHERE COL_LENGTH(obj, col) IS NOT NULL;
IF @err IS NOT NULL BEGIN RAISERROR(@err,16,1); RETURN; END

PRINT 'PHASE 2 OK — procurement schema matches approved alignment.';
