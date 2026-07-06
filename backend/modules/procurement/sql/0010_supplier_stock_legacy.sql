/* ---------------------------------------------------------------------------
   Supplier Live Stock — real backing tables (Sprint: PM supplier fixes).

   procurement.supplier_stock         : per-supplier live stock (imported from the
                                        legacy OrderNMC.SupplierStock and, later,
                                        from Excel uploads). Scoped by tenant/store.
   procurement.supplier_excel_mapping : per supplier+store map of an incoming Excel
                                        column header -> our canonical column
                                        (ported from OrderNMC.SupplierExcelMapping).

   SQL Server 2014 Express safe: no CREATE OR ALTER / DROP IF EXISTS. Idempotent
   via IF OBJECT_ID(...) IS NULL guards.
--------------------------------------------------------------------------- */

IF OBJECT_ID(N'procurement.supplier_stock', N'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_stock (
        supplier_stock_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id             UNIQUEIDENTIFIER NOT NULL,
        store_id              UNIQUEIDENTIFIER NOT NULL,
        supplier_code         VARCHAR(50)  NOT NULL,
        supplier_product_code VARCHAR(50)  NULL,
        supplier_product_name VARCHAR(200) NULL,
        product_code          VARCHAR(50)  NULL,   -- resolved store code (via SupplierProductMatch); may be NULL
        available_stock       FLOAT        NULL,
        ptr                   DECIMAL(18,2) NULL,
        mrp                   DECIMAL(18,2) NULL,
        discount              VARCHAR(50)  NULL,
        packing               VARCHAR(50)  NULL,
        free                  INT          NULL,
        minimum_qty           INT          NULL,
        scheme                INT          NULL,
        transaction_date      DATETIME     NULL,
        source                VARCHAR(20)  NOT NULL DEFAULT 'legacy',  -- legacy | excel
        is_active             BIT          NOT NULL DEFAULT 1,
        imported_by           VARCHAR(100) NULL,
        imported_at           DATETIME     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_supplier_stock PRIMARY KEY (supplier_stock_id)
    );
    CREATE INDEX IX_supplier_stock_scope
        ON procurement.supplier_stock (tenant_id, store_id, supplier_code, is_active);
END
GO

IF OBJECT_ID(N'procurement.supplier_excel_mapping', N'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_excel_mapping (
        mapping_id           UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id            UNIQUEIDENTIFIER NOT NULL,
        store_id             UNIQUEIDENTIFIER NOT NULL,
        supplier_code        VARCHAR(50)   NOT NULL,
        supplier_column_name NVARCHAR(150) NOT NULL,  -- header text in the supplier's Excel
        column_name          NVARCHAR(100) NOT NULL,  -- our canonical column (stock, ptr, mrp, ...)
        is_active            BIT           NOT NULL DEFAULT 1,
        created_by           VARCHAR(100)  NULL,
        created_at           DATETIME      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_supplier_excel_mapping PRIMARY KEY (mapping_id)
    );
    CREATE INDEX IX_supplier_excel_mapping_scope
        ON procurement.supplier_excel_mapping (tenant_id, store_id, supplier_code, is_active);
END
GO
