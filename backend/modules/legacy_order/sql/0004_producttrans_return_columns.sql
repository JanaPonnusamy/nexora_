/* Legacy Order -- Monthly Trend chart: purchase-return column.

   Target database: OrderNMC (central, SQL Server 2014+).
   Idempotent: safe to run more than once. Purely additive (one nullable
   column, metadata-only ALTER) -- does not rewrite existing rows or touch
   the legacy VB.NET desktop client's read/write path.

   Why: the central sync (sync_engine.py) only ever copied a trimmed subset
   of the source Shopaid ProductTrans columns. Sales returns and expiry
   returns are already recoverable centrally from ProductSaleInformation's
   'R'/'ER' series (no schema change needed there), but purchase returns have
   no equivalent granular central source in matching (sale-unit) units --
   PurchaseTrans's own 'PR' series is stored in purchase/pack units and would
   need a per-product conversion factor to line up. ProductTrans's own
   PurchaseReturnQuantity column (same row as PurchaseQuantity, already in
   the right units -- PurchaseQuantity == PurchaseQuantityWithoutReturn +
   PurchaseReturnQuantity, verified against live branch data) is the correct
   source; this migration adds it to the central copy. sync_engine.py's
   ProductTrans projection is updated alongside this migration to populate it
   going forward.
*/

IF COL_LENGTH('dbo.ProductTrans', 'PurchaseReturnQuantity') IS NULL
    ALTER TABLE dbo.ProductTrans ADD PurchaseReturnQuantity FLOAT NULL;
GO
