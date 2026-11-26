/* product_mapping_mirror -- local, same-instance copy of APPROVED rows from
   NEXORA_PLATFORM.dbo.product_mapping, kept inside the legacy central
   database (OrderNMC / OrderSMS / OrderSuccess) so backfill_store_product_codes
   can resolve StoreProductCode locally without a cross-database join at
   read time. Refreshed by modules/supplier_stock_analysis/mirror_sync.py,
   both on a timer and right after a mapping is approved.

   Run this against EACH central database (OrderNMC on .73; OrderSMS and
   OrderSuccess on .32) -- there is no USE statement here on purpose, run it
   with the target database already selected.

   Idempotent: safe to run more than once.
*/

IF OBJECT_ID('dbo.product_mapping_mirror', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_mapping_mirror
    (
        store_name           VARCHAR(50)   NOT NULL,
        source_product_code  VARCHAR(50)   NOT NULL,
        target_product_code  VARCHAR(50)   NOT NULL,
        synced_at            DATETIME      NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (store_name, source_product_code)
    );
END
GO
