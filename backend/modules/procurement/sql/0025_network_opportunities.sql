/* Procurement — Network Opportunities (extends 0024).
   Target database: NEXORA_PLATFORM (SQL Server 2014-compatible).

   Adds the STORE'S OWN per-node facts alongside the network roll-ups already on
   procurement.product_network_movement — the exact same per-store metrics
   network_movement_service.py already computes per node (intelligence_
   repository.store_metrics), just retained instead of discarded after they're
   summed into the network aggregate. No new calculation.

   local_movement_class here is an INFORMATIONAL snapshot only — computed with
   the same decision_rules.movement_class() thresholds, for filtering/display
   in Network Opportunities. It is NOT the authoritative local movement class;
   that remains procurement.procurement_virtual_products.movement_class,
   produced only by the Decision Engine (decision_rules.py / decision_service.py,
   both untouched by this feature).

   Idempotent: safe to re-run.
*/

IF COL_LENGTH('procurement.product_network_movement', 'local_sales_qty') IS NULL
    ALTER TABLE procurement.product_network_movement
        ADD local_sales_qty DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.product_network_movement', 'local_avg_daily_sales') IS NULL
    ALTER TABLE procurement.product_network_movement
        ADD local_avg_daily_sales DECIMAL(18,4) NULL;
GO
IF COL_LENGTH('procurement.product_network_movement', 'local_stock_qty') IS NULL
    ALTER TABLE procurement.product_network_movement
        ADD local_stock_qty DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.product_network_movement', 'local_last_sale_date') IS NULL
    ALTER TABLE procurement.product_network_movement
        ADD local_last_sale_date DATE NULL;
GO
IF COL_LENGTH('procurement.product_network_movement', 'local_movement_class') IS NULL
    ALTER TABLE procurement.product_network_movement
        ADD local_movement_class VARCHAR(20) NULL;
GO

/* Network Opportunities' primary filter (local NONMOVING, network meaningful)
   — supports it directly off the existing per-store lookup index. */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_product_network_movement_opportunities'
      AND object_id = OBJECT_ID('procurement.product_network_movement')
)
    CREATE INDEX IX_product_network_movement_opportunities
        ON procurement.product_network_movement
           (tenant_id, store_id, local_movement_class, network_movement_class)
        INCLUDE (store_product_code, network_sales_qty);
GO
