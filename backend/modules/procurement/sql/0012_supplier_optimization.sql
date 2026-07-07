/* Procurement — Supplier Order Optimization Engine.
   Target database: NEXORA_PLATFORM (SQL Server).

   Adds the two pieces the optimization stage (after Auto Supplier Assignment,
   before Export) needs and that the existing schema does not already hold:

     1. procurement.supplier_min_order  — the per-supplier Minimum Order Value
        used to decide which suppliers are below minimum. Keyed by
        tenant/store/supplier_code so different distributors carry different
        thresholds; blank / 0 means "no minimum" (always exportable).

     2. procurement.optimization_moves  — an audit row for every product moved
        between suppliers, automatic (Accept suggestion) or manual (Manual Move).

   No procurement calculation, VPL, assignment or export logic is changed.
   Moves themselves reuse the existing assignment supplier-change path; this
   table only records them. Idempotent.
*/

IF OBJECT_ID('procurement.supplier_min_order', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_min_order
    (
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NOT NULL,
        supplier_code   VARCHAR(100)     NOT NULL,
        min_order_value DECIMAL(18,2)    NOT NULL DEFAULT 0,
        updated_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_procurement_supplier_min_order
            PRIMARY KEY (tenant_id, store_id, supplier_code)
    );
END
GO

IF OBJECT_ID('procurement.optimization_moves', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.optimization_moves
    (
        move_id        UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id      UNIQUEIDENTIFIER NOT NULL,
        cycle_id       UNIQUEIDENTIFIER NULL,
        refresh_id     UNIQUEIDENTIFIER NOT NULL,
        store_id       UNIQUEIDENTIFIER NULL,
        order_item_id  UNIQUEIDENTIFIER NOT NULL,
        assignment_id  UNIQUEIDENTIFIER NOT NULL,
        product_code   VARCHAR(100)     NULL,
        from_supplier  VARCHAR(100)     NULL,
        to_supplier    VARCHAR(100)     NOT NULL,
        moved_qty      DECIMAL(18,3)    NULL,
        moved_value    DECIMAL(18,2)    NULL,
        reason         VARCHAR(30)      NOT NULL,   /* auto | manual */
        moved_by       UNIQUEIDENTIFIER NULL,
        moved_at       DATETIME         NOT NULL DEFAULT GETDATE(),
        PRIMARY KEY (move_id)
    );

    CREATE INDEX IX_optimization_moves_refresh
        ON procurement.optimization_moves (tenant_id, refresh_id, moved_at);
END
GO
