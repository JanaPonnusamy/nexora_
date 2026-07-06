/* Procurement — Phase 2 (Platform Alignment): Working Order Items
   Target database: NEXORA_PLATFORM (SQL Server).

   procurement.procurement_order_items — the Purchase Manager's working table.
   Generated only from the VPL (rows with suggested_qty > 0). Pending is NOT a
   separate entity: it is remaining_qty on this table.

   Phase 2 changes (approved):
     - PK id -> order_item_id; FK column vpl_id -> refresh_id.
     - item_status supports: draft | review | assigned | partial | skipped
       (no CHECK constraint — platform enforces status values in the service).
     - Audit -> created_at/created_by/updated_at/updated_by (user refs GUID);
       soft delete -> is_deleted/deleted_at/deleted_by; VARCHAR + DATETIME;
       unnamed constraints.

   Idempotent.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

IF OBJECT_ID('procurement.procurement_order_items', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.procurement_order_items
    (
        order_item_id   UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        cycle_id        UNIQUEIDENTIFIER NOT NULL,
        refresh_id      UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NULL,

        product_id      UNIQUEIDENTIFIER NOT NULL,
        product_code    VARCHAR(100)     NULL,

        /* legacy order_items parity */
        final_qty       DECIMAL(18,3)    NULL,
        assigned_qty    DECIMAL(18,3)    NULL,
        remaining_qty   DECIMAL(18,3)    NULL,   /* = Pending */
        action_mode     VARCHAR(30)      NULL,
        manual_override BIT              NULL,
        override_reason VARCHAR(300)     NULL,

        /* draft | review | assigned | partial | skipped */
        item_status     VARCHAR(20)      NOT NULL DEFAULT 'draft',

        /* audit */
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME         NULL,
        updated_by      UNIQUEIDENTIFIER NULL,

        /* soft delete */
        is_deleted      BIT              NOT NULL DEFAULT 0,
        deleted_at      DATETIME         NULL,
        deleted_by      UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (order_item_id),
        FOREIGN KEY (refresh_id)
            REFERENCES procurement.procurement_refreshes (refresh_id),
        UNIQUE (refresh_id, product_id)
    );

    CREATE INDEX IX_procurement_order_items_tenant
        ON procurement.procurement_order_items (tenant_id, is_deleted)
        INCLUDE (refresh_id, cycle_id, item_status);

    CREATE INDEX IX_procurement_order_items_refresh
        ON procurement.procurement_order_items (refresh_id, is_deleted);
END
GO
