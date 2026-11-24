/* Legacy Order -- RunType (Manual / Scheduled) on OrderHeaderDetails.

   Target database: OrderNMC / OrderSMS / OrderSuccess (every tenant's own
   central database -- run this once per tenant database on each HO box).
   Idempotent -- safe to run more than once.

   Owner request (2026-11-24): record whether each order header row came
   from an operator-initiated run (trigger == "manual", written as "Manual")
   or an automated one (the evening scheduler, trigger == "evening", and any
   future automated trigger -- all written as "Scheduled"). See
   order_process.update_order_header_details's run_type computation.

   Existing rows predate this column and have no reliable trigger history to
   backfill from, so they are left NULL rather than guessed at.

   Rollback: DROP COLUMN frees the storage back; see bottom of this file.
*/

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('OrderHeaderDetails') AND name = 'RunType')
    ALTER TABLE OrderHeaderDetails ADD RunType VARCHAR(20) NULL;
GO

/* Rollback (run manually if reverting):
   ALTER TABLE OrderHeaderDetails DROP COLUMN RunType;
*/
