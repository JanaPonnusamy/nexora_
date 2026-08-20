/* Procurement — Product Intelligence: network-wide architecture correction.
   Target database: NEXORA_PLATFORM (SQL Server).

   Corrects the product UNIVERSE of the workspace. The original build (0011)
   anchored on ONE store's Refresh + VPL and resolved outward, so a product the
   anchor store never sold was absent from the anchor VPL and therefore invisible
   to procurement — even when another store sells 400 units a month. The warehouse
   buys for the whole network, so the universe must be the UNION of every selected
   store's VPL.

       Refresh (per store, already multi-store in the Console)
           -> Store VPL  x N            (already persisted per store)
           -> UNION every store VPL     (the product universe)
           -> group into CANONICAL products via dbo.product_mapping
              (whose deterministic edges come from sync.SupplierProductMatch —
               ProductCode is NEVER a cross-store key)
           -> consolidated network demand -> final warehouse purchase qty

   This migration only EXTENDS the 0011 cache tables — no table is dropped and no
   other module's schema is touched. Idempotent: safe to run more than once.
*/

USE NEXORA_PLATFORM;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* ---------------------------------------------------------------------------
   Build header — a build is no longer anchored to a single Refresh. It spans the
   set of stores refreshed together, and names the purchasing WAREHOUSE (the store
   the final procurement quantity is calculated for). refresh_id is retained as
   the warehouse store's Refresh so existing lookups keep working.
--------------------------------------------------------------------------- */
IF COL_LENGTH('procurement.product_intelligence_build', 'warehouse_store_id') IS NULL
    ALTER TABLE procurement.product_intelligence_build
        ADD warehouse_store_id UNIQUEIDENTIFIER NULL;
GO

IF COL_LENGTH('procurement.product_intelligence_build', 'total_need_qty') IS NULL
    ALTER TABLE procurement.product_intelligence_build
        ADD total_need_qty DECIMAL(18,3) NULL;   /* network demand = SUM(store suggested) */
GO

/* ---------------------------------------------------------------------------
   build_store — which store VPLs fed a build (one row per participating store).
   Records the Refresh whose VPL was consumed, so a build is fully reproducible
   and the UI can show "NMC VPL was 3 days old".
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.product_intelligence_build_store', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.product_intelligence_build_store
    (
        build_store_id  UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        build_id        UNIQUEIDENTIFIER NOT NULL,
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NOT NULL,

        refresh_id      UNIQUEIDENTIFIER NULL,   /* the store VPL consumed */
        is_warehouse    BIT              NOT NULL DEFAULT 0,
        vpl_product_count INT            NULL,
        vpl_generated_on  DATETIME       NULL,

        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (build_store_id),
        FOREIGN KEY (build_id)
            REFERENCES procurement.product_intelligence_build (build_id)
    );

    CREATE INDEX IX_pi_build_store_build
        ON procurement.product_intelligence_build_store (build_id);
END
GO

/* ---------------------------------------------------------------------------
   Cache (the canonical product row). Adds the supplier identity the row is
   grouped by, the warehouse-facing numbers the Purchase Manager consumes, and
   the network roll-ups the grid shows.

   consolidated_suggest_qty (0011) keeps its meaning and IS the network demand:
   SUM of every mapped store's suggested qty.

       transfer_qty  = MIN(warehouse stock, network demand)
       purchase_qty  = network demand - transfer_qty
--------------------------------------------------------------------------- */
IF COL_LENGTH('procurement.product_intelligence_cache', 'supplier_code') IS NULL
    ALTER TABLE procurement.product_intelligence_cache
        ADD supplier_code          VARCHAR(50)   NULL,
            supplier_product_code  VARCHAR(100)  NULL,
            supplier_product_name  VARCHAR(300)  NULL;
GO

IF COL_LENGTH('procurement.product_intelligence_cache', 'warehouse_stock_qty') IS NULL
    ALTER TABLE procurement.product_intelligence_cache
        ADD warehouse_stock_qty    DECIMAL(18,3) NULL,
            warehouse_product_code VARCHAR(100)  NULL,   /* NULL = not stocked by the warehouse */
            warehouse_suggest_qty  DECIMAL(18,3) NULL;
GO

IF COL_LENGTH('procurement.product_intelligence_cache', 'total_sales_qty') IS NULL
    ALTER TABLE procurement.product_intelligence_cache
        ADD total_sales_qty        DECIMAL(18,3) NULL,   /* network, rolling window */
            total_purchase_qty     DECIMAL(18,3) NULL;   /* network, rolling window */
GO

IF COL_LENGTH('procurement.product_intelligence_cache', 'priority') IS NULL
    ALTER TABLE procurement.product_intelligence_cache
        ADD priority              VARCHAR(20)   NULL,    /* CRITICAL/HIGH/MEDIUM/LOW/NONE */
            priority_rank         INT           NULL,    /* 4..0, for sorting */
            stockout_store_count  INT           NULL,    /* stores selling it with zero stock */
            confidence            DECIMAL(5,2)  NULL,    /* weakest mapping edge in the group */
            match_method          VARCHAR(20)   NULL;    /* SUPPLIER when fully deterministic */
GO

/* ---------------------------------------------------------------------------
   Store rows — add the per-store facts the merged model needs: whether the store
   contributed a VPL row (real procurement demand) vs. stock-only presence, the
   window sales / purchase totals, and which store is the warehouse.
--------------------------------------------------------------------------- */
IF COL_LENGTH('procurement.product_intelligence_store', 'in_vpl') IS NULL
    ALTER TABLE procurement.product_intelligence_store
        ADD in_vpl        BIT              NOT NULL DEFAULT 0,
            is_warehouse  BIT              NOT NULL DEFAULT 0,
            refresh_id    UNIQUEIDENTIFIER NULL;
GO

IF COL_LENGTH('procurement.product_intelligence_store', 'sales_qty') IS NULL
    ALTER TABLE procurement.product_intelligence_store
        ADD sales_qty     DECIMAL(18,3) NULL,   /* rolling-window sales at this store */
            purchase_qty  DECIMAL(18,3) NULL,   /* rolling-window purchases at this store */
            days_cover    DECIMAL(18,3) NULL;
GO
