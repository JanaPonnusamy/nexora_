/* Procurement — Network Movement Intelligence.
   Target database: NEXORA_PLATFORM (SQL Server 2014-compatible).

   A per-store, informational-only cache: for a product a store already has in
   its own catalogue, what does the SAME canonical product (per dbo.product_mapping)
   look like across every other active store in the tenant right now?

   This is NOT a second procurement engine. It never feeds decision_rules.evaluate,
   never changes procurement_virtual_products, and is looked up by the Order
   Screen the same way offer/supplier context is looked up today — a read-only
   merge keyed by (tenant_id, store_id, store_product_code).

   One row per (tenant_id, store_id, store_product_code) — the store's own
   product code is the lookup key the Order Screen already has on every VPL /
   working-order-item row, so no join through canonical_product_id is needed at
   read time. canonical_product_id groups the rows that came from the same
   union-find component in a given calculation run (informational — not a
   foreign key to any other table).

   Rebuilt wholesale per tenant on each calculation run (same clear+bulk-insert
   pattern as procurement_virtual_products) — never partially updated.

   Idempotent: safe to re-run.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

IF OBJECT_ID('procurement.product_network_movement', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.product_network_movement
    (
        network_movement_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id                UNIQUEIDENTIFIER NOT NULL,
        store_id                 UNIQUEIDENTIFIER NOT NULL,
        store_product_code       VARCHAR(100)     NOT NULL,
        canonical_product_id     UNIQUEIDENTIFIER NOT NULL,

        /* network roll-ups (informational only) */
        network_movement_class   VARCHAR(20)      NULL,
        network_avg_daily_sales  DECIMAL(18,4)    NULL,
        network_sales_qty        DECIMAL(18,3)    NULL,
        network_stock_qty        DECIMAL(18,3)    NULL,
        network_last_sale_date   DATE             NULL,

        /* store-count breakdown behind the classification (buyer explainability) */
        mapped_store_count       INT              NOT NULL DEFAULT 0,
        active_store_count       INT              NOT NULL DEFAULT 0,
        fast_store_count         INT              NOT NULL DEFAULT 0,
        medium_store_count       INT              NOT NULL DEFAULT 0,
        slow_store_count         INT              NOT NULL DEFAULT 0,
        non_moving_store_count   INT              NOT NULL DEFAULT 0,

        /* audit (PR-BR-015-style explainability, reused for this feature) */
        confidence                DECIMAL(5,2)    NULL,
        rolling_days              INT             NULL,
        calculated_at             DATETIME        NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (network_movement_id)
    );

    /* the Order Screen's lookup key — one row per store's own product code */
    CREATE UNIQUE INDEX UX_product_network_movement_lookup
        ON procurement.product_network_movement (tenant_id, store_id, store_product_code);

    /* for "which other stores does this canonical product touch" look-ups */
    CREATE INDEX IX_product_network_movement_canonical
        ON procurement.product_network_movement (tenant_id, canonical_product_id);
END
GO
