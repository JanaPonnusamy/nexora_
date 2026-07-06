/* Add a display-ordering column to dbo.stores for the Stock Availability cards.
   Lower store_order shows first (e.g. warehouse = 1, then NMC = 2, ...).
   Default 100 so unset stores fall after explicitly ordered ones. */
IF COL_LENGTH('dbo.stores', 'store_order') IS NULL
    ALTER TABLE dbo.stores
        ADD store_order INT NOT NULL CONSTRAINT DF_stores_store_order DEFAULT (100);
GO
