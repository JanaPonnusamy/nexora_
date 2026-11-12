/* Procurement — Tenant Export Defaults (desktop Procurement export lock).
   Target database: NEXORA_PLATFORM (SQL Server).

   A single superadmin-owned row per tenant for the desktop stock-client's
   Procurement export card (OwExportCard/exportKit in App.jsx, reused by
   ProcurementWorkspace.jsx): file format + which optional columns are
   included. A restricted role (e.g. SMS_PM) sees these locked to whatever
   a super admin last saved here and cannot edit them in the UI; "rows per
   file" (splitCount) is a per-export runtime value, not stored here, and
   stays freely editable by everyone.

   Idempotent.
*/

IF OBJECT_ID('procurement.tenant_export_defaults', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.tenant_export_defaults
    (
        tenant_id    UNIQUEIDENTIFIER NOT NULL,
        file_format  VARCHAR(10)      NOT NULL DEFAULT 'xls',
        columns      VARCHAR(300)     NULL,  -- comma-separated OW_EXPORT_COLUMN_DEFS keys
        updated_at   DATETIME         NOT NULL DEFAULT GETDATE(),
        updated_by   NVARCHAR(100)    NULL,

        PRIMARY KEY (tenant_id)
    );
END
GO
