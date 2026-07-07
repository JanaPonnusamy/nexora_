/* Procurement — Product Intelligence Workspace (cache tables).
   Target database: NEXORA_PLATFORM (SQL Server).

   The Product Intelligence Workspace extends the existing Refresh/VPL flow; it
   never replaces them. A build reads ONE anchor Refresh + its immutable VPL as
   the source product list, resolves each product across every ACTIVE store via
   the Common Product Mapping (dbo.product_mapping), collects per-store stock +
   suggested quantities, and persists the fully-calculated grid into a cache the
   UI reads directly (the UI never queries transaction tables).

       procurement.product_intelligence_build   (one row per build run — header)
       procurement.product_intelligence_cache    (one row per consolidated product)
       procurement.product_intelligence_store     (one row per product x store)

   The existing procurement.procurement_refreshes IS the "refresh master" the
   spec refers to — no separate refresh_master table is introduced. Store columns
   are NEVER fixed: product_intelligence_store holds one row per store, so the
   store set is fully dynamic (discovered from dbo.stores at build time).

   Platform conventions: <entity>_id UNIQUEIDENTIFIER PK, tenant_id on every row,
   VARCHAR + DATETIME, unnamed inline constraints, is_deleted soft delete on the
   build header. Idempotent: safe to run more than once.
*/

USE NEXORA_PLATFORM;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

/* ---------------------------------------------------------------------------
   product_intelligence_build — one row per build run (the header the grid /
   summary resolve "the latest build" from). A build is scoped to a tenant and
   an anchor Refresh (whose VPL is the source list).
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.product_intelligence_build', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.product_intelligence_build
    (
        build_id         UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id        UNIQUEIDENTIFIER NOT NULL,
        refresh_id       UNIQUEIDENTIFIER NOT NULL,   /* anchor Refresh */
        cycle_id         UNIQUEIDENTIFIER NULL,
        anchor_store_id  UNIQUEIDENTIFIER NULL,

        product_count    INT              NULL,
        store_count      INT              NULL,
        rolling_days     INT              NULL,

        /* consolidated roll-ups (so /summary is a single-row read) */
        total_suggest_qty  DECIMAL(18,3)  NULL,
        total_purchase_qty DECIMAL(18,3)  NULL,
        total_transfer_qty DECIMAL(18,3)  NULL,
        total_stock_qty    DECIMAL(18,3)  NULL,

        status           VARCHAR(30)      NOT NULL DEFAULT 'Ready',
        generated_on     DATETIME         NOT NULL DEFAULT GETDATE(),
        generated_by     UNIQUEIDENTIFIER NULL,

        is_deleted       BIT              NOT NULL DEFAULT 0,
        deleted_at       DATETIME         NULL,

        PRIMARY KEY (build_id)
    );

    CREATE INDEX IX_pi_build_tenant_refresh
        ON procurement.product_intelligence_build (tenant_id, refresh_id, is_deleted)
        INCLUDE (generated_on);
END
GO

/* ---------------------------------------------------------------------------
   product_intelligence_cache — one row per CONSOLIDATED product (the grid row).
   consolidated_suggest = SUM(store suggested); consolidated_purchase =
   MAX(0, SUM(store suggested) - SUM(store stock)). Rows are NEVER removed even
   when purchase = 0 (internal-transfer opportunities stay visible).
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.product_intelligence_cache', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.product_intelligence_cache
    (
        cache_id           UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        build_id           UNIQUEIDENTIFIER NOT NULL,
        tenant_id          UNIQUEIDENTIFIER NOT NULL,
        refresh_id         UNIQUEIDENTIFIER NOT NULL,
        vpl_id             UNIQUEIDENTIFIER NULL,       /* anchor virtual_product_id */
        common_product_id  UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),

        /* anchor product identity (for display without a VPL join) */
        product_code       VARCHAR(100)     NULL,
        product_name       VARCHAR(300)     NULL,
        manufacturer_id    UNIQUEIDENTIFIER NULL,

        /* consolidated calculation outputs */
        consolidated_suggest_qty   DECIMAL(18,3) NOT NULL DEFAULT 0,
        consolidated_purchase_qty  DECIMAL(18,3) NOT NULL DEFAULT 0,
        consolidated_stock_qty     DECIMAL(18,3) NOT NULL DEFAULT 0,
        transfer_qty               DECIMAL(18,3) NOT NULL DEFAULT 0,
        mapped_store_count         INT           NOT NULL DEFAULT 0,

        /* anchor commercial context (detail panel, no extra join) */
        mrp                 DECIMAL(18,4) NULL,
        ptr_cost            DECIMAL(18,4) NULL,
        last_purchase_rate  DECIMAL(18,4) NULL,
        margin              DECIMAL(18,4) NULL,
        offer_text          VARCHAR(200)  NULL,

        generated_on        DATETIME      NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (cache_id),
        FOREIGN KEY (build_id)
            REFERENCES procurement.product_intelligence_build (build_id)
    );

    CREATE INDEX IX_pi_cache_build
        ON procurement.product_intelligence_cache (build_id)
        INCLUDE (product_code, product_name,
                 consolidated_suggest_qty, consolidated_purchase_qty);

    CREATE INDEX IX_pi_cache_tenant
        ON procurement.product_intelligence_cache (tenant_id, refresh_id);
END
GO

/* ---------------------------------------------------------------------------
   product_intelligence_store — one row per (cache product x store). No fixed
   store columns exist anywhere; the store set is dynamic. A cache product with
   NO row for a given store renders as a BLANK cell (product not mapped there).
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.product_intelligence_store', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.product_intelligence_store
    (
        cache_store_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        cache_id           UNIQUEIDENTIFIER NOT NULL,
        build_id           UNIQUEIDENTIFIER NOT NULL,
        tenant_id          UNIQUEIDENTIFIER NOT NULL,
        store_id           UNIQUEIDENTIFIER NOT NULL,

        /* the store's own product identity for this common product */
        product_id         VARCHAR(100)     NULL,   /* store ProductCode */
        product_code       VARCHAR(100)     NULL,
        product_name       VARCHAR(300)     NULL,
        match_method       VARCHAR(20)      NULL,   /* ANCHOR / mapping method */

        stock_qty          DECIMAL(18,3)    NULL,
        suggested_qty      DECIMAL(18,3)    NULL,
        avg_sale           DECIMAL(18,3)    NULL,
        last_sale_date     DATE             NULL,
        last_purchase_date DATE             NULL,
        non_moving_days    INT              NULL,

        created_at         DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (cache_store_id),
        FOREIGN KEY (cache_id)
            REFERENCES procurement.product_intelligence_cache (cache_id)
    );

    CREATE INDEX IX_pi_store_cache
        ON procurement.product_intelligence_store (cache_id);

    CREATE INDEX IX_pi_store_build_store
        ON procurement.product_intelligence_store (build_id, store_id)
        INCLUDE (stock_qty, suggested_qty);
END
GO

/* ---------------------------------------------------------------------------
   Register the module for RBAC (idempotent). The code carries "PROCUREMENT" so
   the access layer maps a grant onto the Procurement workspace capability.
--------------------------------------------------------------------------- */
IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE module_code = 'PROCUREMENT_INTELLIGENCE')
BEGIN
    INSERT INTO dbo.modules (module_id, module_code, module_name, description, is_active)
    VALUES (NEWID(), 'PROCUREMENT_INTELLIGENCE', 'Product Intelligence',
            'Consolidated cross-store procurement intelligence workspace', 1);
END
GO
