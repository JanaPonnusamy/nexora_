/* Procurement — Internal Supplier Stock Distribution: Rack propagation +
   per-stage run status.
   Target database: NEXORA_PLATFORM (SQL Server).

   1) procurement.supplier_stock gets a `rack` column so the internal
      distribution pipeline (NMW -> every store) can carry NMW's own
      PRODUCTS.SubLocation through to the target store's supplier feed --
      the same Rack/SubLocation propagation the legacy port already does
      against the central OrderNMC.SupplierStock table (see
      modules/legacy_order/repository.py replace_supplier_stock +
      sql/0001_supplier_stock_rack.sql). Column is also usable by the
      external Supplier Live Stock importer if a supplier file ever carries
      a rack column.

   2) procurement.distribution_run_item gains separate stock/excel/whatsapp
      stage statuses + per-stage error messages, instead of one combined
      status -- so "WhatsApp failed" never reads as "stock update failed".

   3) procurement.distribution_run gains run-level totals (products, stock
      quantity) for the run-history summary.

   Idempotent.
*/

IF COL_LENGTH('procurement.supplier_stock', 'rack') IS NULL
    ALTER TABLE procurement.supplier_stock ADD rack VARCHAR(50) NULL;
GO

/* `source` was VARCHAR(20) but the 'internal_distribution' tag this
   pipeline writes is 21 chars -- silently truncated on write, which then
   never matched the literal in the DELETE/SELECT WHERE source =
   'internal_distribution' filters used by the replace-on-rerun logic. That
   is a duplicate-accumulation bug: every rerun would INSERT a fresh batch
   without ever deleting the previous one, since the stored value never
   equalled the filter literal. Widen so writes and filters agree. */
IF COL_LENGTH('procurement.supplier_stock', 'source') IS NOT NULL
BEGIN
    DECLARE @srcLen INT = (SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS
                            WHERE TABLE_SCHEMA = 'procurement' AND TABLE_NAME = 'supplier_stock' AND COLUMN_NAME = 'source');
    IF @srcLen IS NOT NULL AND @srcLen < 30
        ALTER TABLE procurement.supplier_stock ALTER COLUMN source VARCHAR(30) NULL;
END
GO

IF COL_LENGTH('procurement.distribution_run_item', 'stock_status') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD stock_status VARCHAR(20) NOT NULL DEFAULT 'skipped';
GO

IF COL_LENGTH('procurement.distribution_run_item', 'stock_error') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD stock_error VARCHAR(1000) NULL;
GO

IF COL_LENGTH('procurement.distribution_run_item', 'excel_status') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD excel_status VARCHAR(20) NOT NULL DEFAULT 'skipped';
GO

IF COL_LENGTH('procurement.distribution_run_item', 'excel_error') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD excel_error VARCHAR(1000) NULL;
GO

IF COL_LENGTH('procurement.distribution_run_item', 'whatsapp_error') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD whatsapp_error VARCHAR(1000) NULL;
GO

IF COL_LENGTH('procurement.distribution_run_item', 'rows_inserted') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD rows_inserted INT NULL;
GO

IF COL_LENGTH('procurement.distribution_run_item', 'rows_skipped') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD rows_skipped INT NULL;
GO

IF COL_LENGTH('procurement.distribution_run', 'total_products') IS NULL
    ALTER TABLE procurement.distribution_run ADD total_products INT NULL;
GO

IF COL_LENGTH('procurement.distribution_run', 'total_stock_qty') IS NULL
    ALTER TABLE procurement.distribution_run ADD total_stock_qty DECIMAL(18,3) NULL;
GO

IF COL_LENGTH('procurement.distribution_run', 'error_summary') IS NULL
    ALTER TABLE procurement.distribution_run ADD error_summary VARCHAR(2000) NULL;
GO

/* Per-store WhatsApp group name, moved onto dbo.stores itself (owner request)
   instead of living only in procurement.distribution_config -- a store's
   WhatsApp group is a property of the store, not of one distribution feed,
   so other features can read it too without importing the procurement
   schema. procurement.distribution_config.whatsapp_group is left in place
   (still used for per-source-store overrides / phone_number / enabled) but
   distribution now reads/writes the group name here first. */
IF COL_LENGTH('dbo.stores', 'w_group_name') IS NULL
    ALTER TABLE dbo.stores ADD w_group_name VARCHAR(200) NULL;
GO

/* One-time backfill from the existing distribution_config rows so nothing
   configured through the old UI is lost by the move. Safe to rerun --
   only fills stores that don't already have a group name set. */
UPDATE s
SET s.w_group_name = c.whatsapp_group
FROM dbo.stores s
JOIN procurement.distribution_config c ON c.tenant_id = s.tenant_id AND c.store_id = s.store_id
WHERE s.w_group_name IS NULL AND c.whatsapp_group IS NOT NULL;
GO
