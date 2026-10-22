/* Legacy Order -- IsActive flag on OrderSuppliers.

   Target database: OrderNMC (central, SQL Server 2014 Express).
   Idempotent -- safe to run more than once.

   Problem: the Order Workspace supplier picker (repository.list_suppliers)
   needs to exclude confirmed-inactive suppliers, but OrderSuppliers never
   carried an active/inactive flag of its own -- it previously had to join
   back live to the branch's Suppliers table (or sync.Suppliers for an
   agent-synced store) on every search keystroke.

   Fix: sync_engine's Suppliers->OrderSuppliers projection now carries
   IsActive through (see get_query_for_table/platform_query_for_table), and
   sync_table lazily adds this column via _ensure_supplier_isactive_column
   the next time Suppliers syncs for ANY store. This migration exists only
   to add the column immediately (rather than waiting on the next sync run)
   and backfill existing rows from the live Suppliers table in one pass, so
   the picker reflects real status right away instead of leaving every
   pre-existing row NULL until its store's next sync.

   Rollback: DROP COLUMN frees the bit storage back; see bottom of this file.
*/

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('OrderSuppliers') AND name = 'IsActive')
    ALTER TABLE OrderSuppliers ADD IsActive BIT NULL;
GO

/* One-time backfill: match each OrderSuppliers row to the branch Suppliers
   master by (suppliercode, StoreName) and copy its isActive value. Only
   touches rows still NULL, so a later real sync's fresher value is never
   clobbered by re-running this script. */
UPDATE os
SET os.IsActive = CAST(s.isActive AS BIT)
FROM OrderSuppliers os
JOIN Suppliers s
  ON s.suppliercode COLLATE SQL_Latin1_General_CP1_CI_AS
     = os.suppliercode COLLATE SQL_Latin1_General_CP1_CI_AS
 AND s.StoreName = os.StoreName
WHERE os.IsActive IS NULL;
GO

/* Rollback (run manually if reverting):
   ALTER TABLE OrderSuppliers DROP COLUMN IsActive;
*/
