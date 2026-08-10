/* Legacy Order -- NMW Stock -> All Stores: propagate NMW's product SubLocation
   (PRODUCTS.SubLocation on the branch DB) into the central SupplierStock row
   as a Rack column.
   Target database: OrderNMC (central, SQL Server).

   Idempotent -- safe to run more than once.
*/

IF COL_LENGTH('SupplierStock', 'Rack') IS NULL
    ALTER TABLE SupplierStock
        ADD Rack VARCHAR(50) NULL;
GO
