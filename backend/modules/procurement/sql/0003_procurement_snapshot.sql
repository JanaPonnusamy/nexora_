/* Procurement — Sprint 3: Procurement Snapshot Engine
   Target database: NEXORA_PLATFORM (SQL Server).

   Adds RAW snapshot value columns to procurement_virtual_products and snapshot
   refresh-tracking columns to the VPL header. Also defines the single source
   integration procedure the engine calls to load operational data.

   These are raw operational values ONLY — current stock, pending, last
   purchase/sale, averages, expiry, supplier counts. No calculated order
   quantities, supplier assignment, pending/expiry/shortage engines or PO logic
   live here (later sprints).

   Idempotent: column adds are guarded by COL_LENGTH; the procedure uses
   CREATE OR ALTER. Safe to re-run.
*/

/* ---------------------------------------------------------------------------
   1. Raw snapshot columns on procurement.procurement_virtual_products
--------------------------------------------------------------------------- */
IF COL_LENGTH('procurement.procurement_virtual_products', 'current_stock_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD current_stock_qty     DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'available_stock_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD available_stock_qty   DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'pending_purchase_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD pending_purchase_qty  DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'pending_sales_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD pending_sales_qty     DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'last_purchase_date') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD last_purchase_date    DATE NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'last_purchase_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD last_purchase_qty     DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'last_purchase_rate') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD last_purchase_rate    DECIMAL(18,4) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'last_sale_date') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD last_sale_date        DATE NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'last_sale_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD last_sale_qty         DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'avg_daily_sales') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD avg_daily_sales       DECIMAL(18,4) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'avg_monthly_sales') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD avg_monthly_sales     DECIMAL(18,4) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'expiry_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD expiry_qty            DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'near_expiry_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD near_expiry_qty       DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'supplier_count') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD supplier_count        INT NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'preferred_supplier_id') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD preferred_supplier_id UNIQUEIDENTIFIER NULL;
GO
/* Per-product snapshot refresh tracking (drives "changed" refresh + progress) */
IF COL_LENGTH('procurement.procurement_virtual_products', 'snapshot_refreshed_on') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD snapshot_refreshed_on DATETIME NULL;
GO

/* ---------------------------------------------------------------------------
   2. Snapshot tracking on the Refresh header
   (also created by 0002 for fresh installs; guarded here for older DBs)
--------------------------------------------------------------------------- */
IF COL_LENGTH('procurement.procurement_refreshes', 'last_snapshot_on') IS NULL
    ALTER TABLE procurement.procurement_refreshes
        ADD last_snapshot_on DATETIME NULL;
GO
IF COL_LENGTH('procurement.procurement_refreshes', 'last_snapshot_by') IS NULL
    ALTER TABLE procurement.procurement_refreshes
        ADD last_snapshot_by UNIQUEIDENTIFIER NULL;
GO

/* ---------------------------------------------------------------------------
   3. Source integration procedure
   ---------------------------------------------------------------------------
   The Snapshot Engine calls this to obtain RAW operational values for the
   products in a VPL. It returns one row per VPL product with every raw
   snapshot column.

   Base set = the live products already in the VPL (procurement schema, owned
   here). The operational values are produced by the LEFT JOINs in the marked
   block below — THAT BLOCK IS THE SINGLE INTEGRATION POINT. Until the platform
   team wires the real operational sources (inventory / sales / purchase /
   pending / expiry / supplier), the LEFT JOINs yield no rows and COALESCE
   returns a neutral empty snapshot (0 / NULL). No business rules are assumed
   here; wiring the joins does not change the engine, repository or API.

   Params:
     @TenantId  required  — tenant isolation
     @VplId     required  — which VPL's products to source
     @ProductId optional  — when supplied, restrict to a single product
--------------------------------------------------------------------------- */
GO
IF OBJECT_ID('procurement.usp_VplSnapshotSource', 'P') IS NOT NULL
    DROP PROCEDURE procurement.usp_VplSnapshotSource;
GO
CREATE PROCEDURE procurement.usp_VplSnapshotSource
    @TenantId  UNIQUEIDENTIFIER,
    @VplId     UNIQUEIDENTIFIER,
    @ProductId UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        vp.product_id,

        /* ---- raw operational values (COALESCE -> neutral empty snapshot) ---- */
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS current_stock_qty,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS available_stock_qty,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS pending_purchase_qty,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS pending_sales_qty,
        CAST(NULL                 AS DATE)          AS last_purchase_date,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS last_purchase_qty,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,4)) AS last_purchase_rate,
        CAST(NULL                 AS DATE)          AS last_sale_date,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS last_sale_qty,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,4)) AS avg_daily_sales,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,4)) AS avg_monthly_sales,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS expiry_qty,
        CAST(COALESCE(NULL, 0)    AS DECIMAL(18,3)) AS near_expiry_qty,
        CAST(COALESCE(NULL, 0)    AS INT)           AS supplier_count,
        CAST(NULL AS UNIQUEIDENTIFIER)              AS preferred_supplier_id

    FROM procurement.procurement_virtual_products vp
    /* @VplId matches the owning Refresh (column renamed vpl_id -> refresh_id) */
    /* ===================== INTEGRATION POINT (wire below) =====================
       LEFT JOIN <inventory source>  inv ON inv.product_id = vp.product_id AND ...
       LEFT JOIN <sales summary>     sal ON ...
       LEFT JOIN <purchase summary>  pur ON ...
       LEFT JOIN <pending txns>      pen ON ...
       LEFT JOIN <expiry source>     exp ON ...
       LEFT JOIN <supplier source>   sup ON ...
       Then replace the COALESCE(NULL, ...) expressions above with the joined
       columns. Keep the output column list and order unchanged.
       ======================================================================= */
    WHERE vp.tenant_id = @TenantId
      AND vp.refresh_id = @VplId
      AND (@ProductId IS NULL OR vp.product_id = @ProductId);
END
GO
