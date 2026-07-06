/* Procurement — Phase 2 (Platform Alignment): Refresh + Virtual Products
   Target database: NEXORA_PLATFORM (SQL Server).

   A Refresh is one immutable procurement snapshot; it owns exactly one Virtual
   Product List.

       procurement.procurement_refreshes          (header, PK refresh_id)
       procurement.procurement_virtual_products    (detail,  PK virtual_product_id)

   Phase 2 changes (approved):
     - PK renamed id -> refresh_id / virtual_product_id (platform <entity>_id).
     - FK column vpl_id -> refresh_id (it always referenced the Refresh).
     - Refresh now stores the snapshot PARAMETERS: rolling_days (moved from the
       Cycle), previous_refresh_id, snapshot_grn_number, snapshot_sale_bill_number,
       sync_execution_id. previous_pending_ref is intentionally NOT added —
       Pending is derived from previous_refresh_id + remaining_qty > 0.
       generation_duration is NOT stored (derived from the start/end timestamps).
     - Virtual Products gained effective_available_qty and pending_used_qty.
     - Audit -> created_at/created_by/updated_at/updated_by (user refs GUID);
       soft delete -> is_deleted/deleted_at/deleted_by; VARCHAR + DATETIME;
       unnamed constraints; snapshot_status CHECK dropped (enforced in service).

   Idempotent: safe to re-run.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

/* ---------------------------------------------------------------------------
   procurement.procurement_refreshes  — one immutable snapshot per run
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.procurement_refreshes', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.procurement_refreshes
    (
        refresh_id      UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        cycle_id        UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NULL,
        snapshot_name   VARCHAR(200)     NOT NULL,
        snapshot_status VARCHAR(50)      NOT NULL DEFAULT 'Draft',

        /* immutable snapshot parameters (every Refresh is reproducible) */
        refresh_no                 INT              NULL,
        rolling_days               INT              NULL,   /* moved from Cycle */
        min_days                   DECIMAL(18,2)    NULL,
        max_days                   DECIMAL(18,2)    NULL,
        previous_refresh_id        UNIQUEIDENTIFIER NULL,
        snapshot_grn_number        VARCHAR(50)      NULL,
        snapshot_sale_bill_number  VARCHAR(50)      NULL,
        sync_execution_id          UNIQUEIDENTIFIER NULL,   /* -> sync_execution */

        /* generation tracking (duration is DERIVED from these, not stored) */
        generated_product_count INT           NULL,
        generation_started_at   DATETIME      NULL,
        generation_completed_at DATETIME      NULL,
        remarks                 VARCHAR(500)  NULL,
        last_snapshot_on        DATETIME      NULL,
        last_snapshot_by        UNIQUEIDENTIFIER NULL,

        /* audit */
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME         NULL,
        updated_by      UNIQUEIDENTIFIER NULL,

        /* soft delete */
        is_deleted      BIT              NOT NULL DEFAULT 0,
        deleted_at      DATETIME         NULL,
        deleted_by      UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (refresh_id),
        FOREIGN KEY (cycle_id) REFERENCES procurement.procurement_cycles (cycle_id)
    );

    CREATE INDEX IX_procurement_refreshes_tenant
        ON procurement.procurement_refreshes (tenant_id, is_deleted)
        INCLUDE (cycle_id, store_id, snapshot_status);

    CREATE INDEX IX_procurement_refreshes_cycle
        ON procurement.procurement_refreshes (cycle_id, is_deleted);
END
GO

/* ---------------------------------------------------------------------------
   procurement.procurement_virtual_products  — immutable VPL detail rows
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.procurement_virtual_products', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.procurement_virtual_products
    (
        virtual_product_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id        UNIQUEIDENTIFIER NOT NULL,
        cycle_id         UNIQUEIDENTIFIER NOT NULL,
        refresh_id       UNIQUEIDENTIFIER NOT NULL,   /* owning Refresh */
        product_id       UNIQUEIDENTIFIER NOT NULL,
        product_code     VARCHAR(100)     NULL,
        product_name     VARCHAR(300)     NULL,
        manufacturer_id  UNIQUEIDENTIFIER NULL,
        category_id      UNIQUEIDENTIFIER NULL,
        schedule_type    VARCHAR(50)      NULL,
        unit             VARCHAR(50)      NULL,
        is_active        BIT              NOT NULL DEFAULT 1,
        snapshot_version INT              NOT NULL DEFAULT 1,

        /* product attributes */
        mrp                       DECIMAL(18,4) NULL,
        ptr_cost                  DECIMAL(18,4) NULL,
        pack                      VARCHAR(50)   NULL,
        unit_description          VARCHAR(100)  NULL,
        sub_location              VARCHAR(100)  NULL,

        /* sales / movement metrics */
        monthly_sales_qty         DECIMAL(18,3) NULL,
        tx_count                  INT           NULL,
        max_day_sale_qty          DECIMAL(18,3) NULL,
        max_bill_qty              DECIMAL(18,3) NULL,
        days_since_last_sale      INT           NULL,
        days_since_last_purchase  INT           NULL,
        days_cover                DECIMAL(18,3) NULL,
        movement_class            VARCHAR(30)   NULL,
        stock_status              VARCHAR(30)   NULL,

        /* offer / scheme */
        offer_buy_qty             DECIMAL(18,3) NULL,
        offer_free_qty            DECIMAL(18,3) NULL,
        offer_last_date           DATE          NULL,

        /* workflow / flags */
        order_type                VARCHAR(30)   NULL,
        is_auto_accept            BIT           NULL,
        warning_flag              BIT           NULL,
        warning_reason            VARCHAR(200)  NULL,
        committed_qty             DECIMAL(18,3) NULL,
        remaining_procurement_qty DECIMAL(18,3) NULL,

        /* decision outputs (Calculation Engine sprint — schema only) */
        required_qty              DECIMAL(18,3) NULL,
        suggested_qty             DECIMAL(18,3) NULL,
        target_days               DECIMAL(18,2) NULL,
        target_stock_qty          DECIMAL(18,3) NULL,
        raw_required_qty          DECIMAL(18,3) NULL,
        final_required_qty        DECIMAL(18,3) NULL,
        procurement_action        VARCHAR(50)   NULL,
        trigger_reason            VARCHAR(100)  NULL,

        /* Phase 2: decision explainability (Effective Available, Pending Used) */
        effective_available_qty   DECIMAL(18,3) NULL,
        pending_used_qty          DECIMAL(18,3) NULL,

        created_at       DATETIME         NOT NULL DEFAULT GETDATE(),
        updated_at       DATETIME         NULL,

        PRIMARY KEY (virtual_product_id),
        FOREIGN KEY (refresh_id)
            REFERENCES procurement.procurement_refreshes (refresh_id),
        UNIQUE (refresh_id, product_id)
    );

    CREATE INDEX IX_procurement_virtual_products_refresh
        ON procurement.procurement_virtual_products (refresh_id, is_active)
        INCLUDE (product_code, product_name);

    CREATE INDEX IX_procurement_virtual_products_tenant
        ON procurement.procurement_virtual_products (tenant_id, refresh_id);
END
GO
