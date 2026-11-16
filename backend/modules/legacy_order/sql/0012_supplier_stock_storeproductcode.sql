/* Supplier Stock Analysis "By Supplier -> Live Stock" was joining
   SupplierStock to SupplierProductMatch on every read (cross-database,
   large row counts at stores like SMG/supplier 292) to resolve each
   supplier row's matching store product code. This column caches that
   resolution on SupplierStock itself at IMPORT time, so reads need only
   SupplierStock -- no SupplierProductMatch join at all.

   StoreProductCode is kept in sync by the stock-import code paths
   (supplier_stock_analysis.repository, legacy_order.repository) whenever a
   row is inserted/replaced, reading SupplierProductMatch.ProductCode for
   that (storename, suppliercode, supplierproductcode) at import time.

   Target database: OrderNMC / OrderSMS / OrderSuccess (central, SQL Server).
   Idempotent -- safe to run more than once, and on any of the three.
*/

IF COL_LENGTH('SupplierStock', 'StoreProductCode') IS NULL
    ALTER TABLE SupplierStock
        ADD StoreProductCode VARCHAR(50) NULL;
GO

-- One-time backfill from the existing SupplierProductMatch join, so rows
-- already imported before this column existed don't show as unmapped
-- until their next re-import.
UPDATE ss
    SET ss.StoreProductCode = spm.ProductCode
FROM SupplierStock ss
JOIN SupplierProductMatch spm
  ON spm.StoreName = ss.storename
 AND spm.SupplierCode = ss.suppliercode
 AND spm.SupplierProductCode = ss.supplierproductcode
WHERE ss.StoreProductCode IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_SupplierStock_Store_Supplier' AND object_id = OBJECT_ID('SupplierStock')
)
    CREATE INDEX IX_SupplierStock_Store_Supplier
        ON SupplierStock (storename, suppliercode) INCLUDE (StoreProductCode, stock);
GO
