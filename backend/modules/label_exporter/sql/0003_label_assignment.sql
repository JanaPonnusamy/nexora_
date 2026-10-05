-- Label Exporter: location-assignment workflow.
--
-- Extends dbo.label_review from a bare Y/N+remarks review row into the full
-- review + unit-correction + location-assignment record described in the
-- redesign spec (§K), and adds the location audit trail (§L).
--
-- IMPORTANT (Conflict A ruling): assigned_sublocation here is the SOURCE OF
-- TRUTH for a product's shelf box. We never write sync.Products.SubLocation
-- (that mirror flows FROM the store and would overwrite us on the next sync).
-- Pushing these assignments down to the store's own SQL Server is a separate,
-- later step.
--
-- Idempotent: every ADD/CREATE is guarded, so ensure_schema() can run it on
-- every startup. Batches are separated by GO for the split-on-GO applier.

IF COL_LENGTH('dbo.label_review', 'product_name') IS NULL
    ALTER TABLE dbo.label_review ADD product_name NVARCHAR(200) NULL;
GO
IF COL_LENGTH('dbo.label_review', 'old_unit_description') IS NULL
    ALTER TABLE dbo.label_review ADD old_unit_description NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.label_review', 'unit_description') IS NULL
    ALTER TABLE dbo.label_review ADD unit_description NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.label_review', 'old_sublocation') IS NULL
    ALTER TABLE dbo.label_review ADD old_sublocation NVARCHAR(50) NULL;
GO
IF COL_LENGTH('dbo.label_review', 'assigned_sublocation') IS NULL
    ALTER TABLE dbo.label_review ADD assigned_sublocation NVARCHAR(50) NULL;
GO
IF COL_LENGTH('dbo.label_review', 'assignment_mode') IS NULL
    ALTER TABLE dbo.label_review ADD assignment_mode NVARCHAR(20) NULL;   -- continue / new_label / single
GO
IF COL_LENGTH('dbo.label_review', 'assignment_type') IS NULL
    ALTER TABLE dbo.label_review ADD assignment_type NVARCHAR(30) NULL;   -- standard_box / single_product_box
GO
IF COL_LENGTH('dbo.label_review', 'assigned_by') IS NULL
    ALTER TABLE dbo.label_review ADD assigned_by UNIQUEIDENTIFIER NULL;
GO
IF COL_LENGTH('dbo.label_review', 'assigned_at') IS NULL
    ALTER TABLE dbo.label_review ADD assigned_at DATETIME2 NULL;
GO
IF COL_LENGTH('dbo.label_review', 'label_required') IS NULL
    ALTER TABLE dbo.label_review ADD label_required BIT NULL;
GO
IF COL_LENGTH('dbo.label_review', 'label_created_at') IS NULL
    ALTER TABLE dbo.label_review ADD label_created_at DATETIME2 NULL;
GO
IF COL_LENGTH('dbo.label_review', 'stock') IS NULL
    ALTER TABLE dbo.label_review ADD stock DECIMAL(18, 2) NULL;
GO
IF COL_LENGTH('dbo.label_review', 'sale_days') IS NULL
    ALTER TABLE dbo.label_review ADD sale_days INT NULL;
GO
IF COL_LENGTH('dbo.label_review', 'purchase_days') IS NULL
    ALTER TABLE dbo.label_review ADD purchase_days INT NULL;
GO

-- Fast lookup of currently-assigned boxes for a store (occupancy + label queue).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_label_review_assigned'
      AND object_id = OBJECT_ID('dbo.label_review')
)
    CREATE INDEX IX_label_review_assigned
        ON dbo.label_review (tenant_id, store_id, assigned_sublocation)
        INCLUDE (product_code, unit_description, label_required);
GO

-- Location change audit trail (§L). Never destroy the previous box silently.
IF OBJECT_ID('dbo.label_location_history', 'U') IS NULL
    CREATE TABLE dbo.label_location_history (
        id                UNIQUEIDENTIFIER NOT NULL
                          CONSTRAINT PK_label_location_history PRIMARY KEY
                          CONSTRAINT DF_label_loc_hist_id DEFAULT NEWID(),
        tenant_id         UNIQUEIDENTIFIER NOT NULL,
        store_id          UNIQUEIDENTIFIER NOT NULL,
        product_code      NVARCHAR(50) NOT NULL,
        old_location      NVARCHAR(50) NULL,
        new_location      NVARCHAR(50) NULL,
        unit_description  NVARCHAR(100) NULL,
        assignment_mode   NVARCHAR(20) NULL,
        assignment_type   NVARCHAR(30) NULL,
        assigned_by       UNIQUEIDENTIFIER NULL,
        assigned_at       DATETIME2 NOT NULL
                          CONSTRAINT DF_label_loc_hist_at DEFAULT SYSUTCDATETIME()
    );
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_label_location_history_product'
      AND object_id = OBJECT_ID('dbo.label_location_history')
)
    CREATE INDEX IX_label_location_history_product
        ON dbo.label_location_history (tenant_id, store_id, product_code, assigned_at);
GO
