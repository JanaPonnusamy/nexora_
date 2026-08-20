-- Adds an explicit warehouse flag to dbo.stores so the central-ordering
-- (Supplier Stock Analysis) screen can resolve each tenant's warehouse from the
-- data instead of hardcoding the 'NMW' store code. A tenant may have more than
-- one warehouse; a super admin picks which one to order for.
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'stores' AND COLUMN_NAME = 'is_warehouse'
)
BEGIN
    ALTER TABLE dbo.stores
        ADD is_warehouse BIT NOT NULL CONSTRAINT DF_stores_is_warehouse DEFAULT 0;
END
GO

-- Seed existing warehouses: the 'NMW' branch is the Nathan Medicals warehouse,
-- and (defensively) any store seeded as store_order = 1 (the warehouse slot).
UPDATE dbo.stores
   SET is_warehouse = 1
 WHERE UPPER(LTRIM(RTRIM(store_code))) = 'NMW'
    OR store_order = 1;
GO
