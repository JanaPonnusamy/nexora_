/* Procurement — Per-Supplier Export Settings (Export Monitor overhaul).
   Target database: NEXORA_PLATFORM (SQL Server).

   Remembers each supplier's own Export Document choices (format, which
   optional columns, the renamed Order Qty header, sort-by, and the desktop
   export folder) so the Export Settings dialog pre-fills with what was used
   last time for THAT supplier — no need to reconfigure every export.

   Deliberately its own table, not new columns on sync.Suppliers: these are
   pure export-UI preferences, not legacy-synced supplier master data, and
   sync.Suppliers.auto_assign/min_products/export_rank (migrations 0015/0016)
   already carry a sync-job-overwrite caveat that a table like this avoids
   entirely by living outside sync.* altogether.

   Idempotent.
*/

IF OBJECT_ID('procurement.supplier_export_settings', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_export_settings
    (
        tenant_id           UNIQUEIDENTIFIER NOT NULL,
        store_id            UNIQUEIDENTIFIER NOT NULL,
        supplier_code       VARCHAR(100)     NOT NULL,
        format              VARCHAR(10)      NOT NULL DEFAULT 'excel',
        columns             VARCHAR(200)     NULL,  -- comma-separated optional column keys
        order_qty_header    VARCHAR(40)      NULL,
        sort_by             VARCHAR(30)      NULL,
        export_folder_path  NVARCHAR(500)    NULL,
        updated_at          DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (tenant_id, store_id, supplier_code)
    );
END
GO
