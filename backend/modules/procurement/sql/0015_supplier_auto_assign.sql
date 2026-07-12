/* Procurement — Auto Assign Suppliers eligibility.
   Target database: NEXORA_PLATFORM (SQL Server), table: sync.Suppliers.

   Two new columns directly on the synced supplier master (owner-directed —
   no separate procurement.* overlay table):
     - auto_assign (bit, default 1): whether this supplier is eligible to
       receive an Auto Assign Suppliers assignment at all. Defaults to 1 so
       existing behaviour (every supplier with purchase history is a
       candidate) does not regress; a buyer opts a supplier OUT, not in.
     - min_products (int, default 2): Auto Assign only actually commits a
       batch to this supplier if the run would give them at least this many
       products; otherwise those products are left unassigned for manual
       review rather than trickling a single lonely line to the supplier.

   NOTE: sync.* tables are repopulated by the legacy sync job. If that job
   ever does a full table rebuild (drop/recreate) instead of an in-place
   MERGE, these two columns will be silently lost — confirm the sync
   process only upserts existing rows before relying on this long-term.

   Idempotent (SQL Server 2014 — no column-exists-safe ADD COLUMN, guarded
   manually via sys.columns).
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('sync.Suppliers') AND name = 'auto_assign'
)
    ALTER TABLE sync.Suppliers ADD auto_assign BIT NOT NULL DEFAULT 1;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('sync.Suppliers') AND name = 'min_products'
)
    ALTER TABLE sync.Suppliers ADD min_products INT NOT NULL DEFAULT 2;
GO
