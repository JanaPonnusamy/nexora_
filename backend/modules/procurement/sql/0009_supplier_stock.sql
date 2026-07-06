/* Procurement — Sprint 2 (Workspace Completion): Supplier Live Stock.
   Target database: NEXORA_PLATFORM (SQL Server).

   Import target for a supplier's live/available stock file. Rows are populated
   by the Supplier Stock importer (Excel today; Selenium / API later) and read
   back — already resolved to store ProductCodes — by the read-only endpoint
   GET /api/procurement/refreshes/{refresh_id}/supplier-stock.

   No procurement calculation, VPL, assignment or export logic depends on this
   table. product_code is resolved at import time via dbo/sync SupplierProductMatch
   so the read endpoint performs no mapping logic. Idempotent.
*/

IF OBJECT_ID('procurement.supplier_stock', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_stock
    (
        supplier_stock_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id             UNIQUEIDENTIFIER NOT NULL,
        store_id              UNIQUEIDENTIFIER NULL,
        supplier_code         VARCHAR(100)     NOT NULL,
        supplier_product_code VARCHAR(100)     NULL,
        supplier_product_name VARCHAR(300)     NULL,
        product_code          VARCHAR(100)     NULL,   /* resolved at import */
        available_stock       DECIMAL(18,3)    NULL,
        ptr                   DECIMAL(18,4)    NULL,
        mrp                   DECIMAL(18,4)    NULL,
        discount              DECIMAL(18,3)    NULL,
        packing               VARCHAR(50)      NULL,
        scheme                VARCHAR(100)     NULL,
        free                  DECIMAL(18,3)    NULL,
        minimum_qty           DECIMAL(18,3)    NULL,
        transaction_date      DATE             NULL,
        source                VARCHAR(30)      NULL,   /* excel | selenium | api */
        imported_at           DATETIME         NOT NULL DEFAULT GETDATE(),
        imported_by           UNIQUEIDENTIFIER NULL,
        is_active             BIT              NOT NULL DEFAULT 1,
        PRIMARY KEY (supplier_stock_id)
    );

    CREATE INDEX IX_supplier_stock_lookup
        ON procurement.supplier_stock (tenant_id, supplier_code, is_active)
        INCLUDE (product_code, available_stock);
END
GO
