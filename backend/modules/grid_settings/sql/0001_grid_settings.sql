-- Generic per-user, per-grid display settings (column order, widths,
-- padding/density). One table serves every grid in the app — grid_key is
-- an arbitrary caller-chosen string (e.g. "pm.purchaseHistory",
-- "pm.salesHistory") so new grids never need a new table or migration.
-- Documentation-only: repository.ensure_schema() creates this at runtime.
IF OBJECT_ID('dbo.user_grid_settings', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_grid_settings (
        user_id      UNIQUEIDENTIFIER NOT NULL,
        grid_key     NVARCHAR(100)    NOT NULL,
        tenant_id    UNIQUEIDENTIFIER NULL,
        settings     NVARCHAR(MAX)    NOT NULL,  -- JSON: { columnOrder, columnWidths, padding, ... }
        updated_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_user_grid_settings PRIMARY KEY (user_id, grid_key)
    );
END
