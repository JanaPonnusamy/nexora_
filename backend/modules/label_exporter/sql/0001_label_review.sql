-- Label review: per-product decisions made while walking the shelf
-- letter-by-letter (include on label sheet Y/N, counter/consumer type,
-- and a suggested UnitDescription correction pending super-admin approval).
-- Lives in the platform DB only for now - approved suggestions are not yet
-- written back to the store's own SQL Server (that's a separate, later step).

IF OBJECT_ID('dbo.label_review', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.label_review (
        id                          UNIQUEIDENTIFIER NOT NULL
                                    CONSTRAINT PK_label_review PRIMARY KEY
                                    CONSTRAINT DF_label_review_id DEFAULT NEWID(),
        tenant_id                   UNIQUEIDENTIFIER NOT NULL,
        store_id                    UNIQUEIDENTIFIER NOT NULL,
        product_code                NVARCHAR(50) NOT NULL,
        include_label               CHAR(1) NULL,       -- 'Y' / 'N', NULL = not reviewed yet
        product_kind                NVARCHAR(20) NULL,  -- 'counter' / 'consumer'
        suggested_unit_description  NVARCHAR(100) NULL,
        suggestion_status           NVARCHAR(20) NOT NULL
                                    CONSTRAINT DF_label_review_suggestion_status DEFAULT 'none',
                                    -- none / pending / approved / rejected
        final_unit_description      NVARCHAR(100) NULL, -- set on approval, may differ from the suggestion
        reviewed_by                 UNIQUEIDENTIFIER NULL,
        reviewed_at                 DATETIME2 NULL,
        suggested_by                UNIQUEIDENTIFIER NULL,
        suggested_at                DATETIME2 NULL,
        decided_by                  UNIQUEIDENTIFIER NULL,
        decided_at                  DATETIME2 NULL,
        created_at                  DATETIME2 NOT NULL
                                    CONSTRAINT DF_label_review_created DEFAULT SYSUTCDATETIME(),
        updated_at                  DATETIME2 NOT NULL
                                    CONSTRAINT DF_label_review_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_label_review_product UNIQUE (tenant_id, store_id, product_code)
    );

    CREATE INDEX IX_label_review_suggestion_status
        ON dbo.label_review (tenant_id, store_id, suggestion_status);
END;
