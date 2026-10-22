/* Legacy Order -- precomputed IsOffer flag on OrderManagement.

   Target database: OrderNMC (central, SQL Server 2014 Express).
   Idempotent -- safe to run more than once.

   Problem: qty_check_rows/pending_order_rows computed the grid's "has had a
   free-qty offer" (🎁) column live, per row, via a correlated EXISTS against
   PurchaseTrans (repository._OFFER_HISTORY_EXISTS). For a store with many
   open rows and a large PurchaseTrans table (e.g. NMS: 1385 rows x 278K
   PurchaseTrans rows), that is one subquery execution per grid row at EVERY
   screen load -- measured live at 77s for NMS's qty_check_rows (vs 13ms for
   a store with 0 open rows), comfortably exceeding the desktop client's 45s
   request timeout and surfacing as "Request timed out after 45s" with a
   misleading "every pending product has been reviewed" empty state.

   Fix: compute the flag ONCE per product, in a single set-based UPDATE, at
   order-generation time (order_process.insert_data_into_destination) instead
   of on every grid read. The grid query then becomes a plain
   `SELECT ... FROM OrderManagement WHERE StoreName = ? AND ...` with no join
   at all for this column.

   This migration only adds the column (default 0, backfilled separately by
   the backend on first deploy -- see repository.backfill_is_offer). It does
   not change existing PurchaseTrans indexes; the one-time backfill and the
   ongoing per-run UPDATE both still scan PurchaseTrans, but only once per
   DISTINCT ProductCode in the run, not once per OrderManagement row, which
   is the actual fix (that distinct-product set is typically far smaller
   than the row count, and PurchaseTrans is read once per run, not once per
   grid load).

   Rollback: DROP COLUMN frees the bit storage back; see bottom of this file.
*/

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('OrderManagement') AND name = 'IsOffer')
    ALTER TABLE OrderManagement ADD IsOffer BIT NOT NULL CONSTRAINT DF_OrderManagement_IsOffer DEFAULT 0;
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('OrderManagementBackup') AND name = 'IsOffer')
    ALTER TABLE OrderManagementBackup ADD IsOffer BIT NOT NULL CONSTRAINT DF_OrderManagementBackup_IsOffer DEFAULT 0;
GO

/* Rollback (run manually if reverting):
   ALTER TABLE OrderManagement DROP CONSTRAINT DF_OrderManagement_IsOffer;
   ALTER TABLE OrderManagement DROP COLUMN IsOffer;
   ALTER TABLE OrderManagementBackup DROP CONSTRAINT DF_OrderManagementBackup_IsOffer;
   ALTER TABLE OrderManagementBackup DROP COLUMN IsOffer;
*/
