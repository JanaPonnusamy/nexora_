/* Legacy Order sync -- Batches zero-out stall fix.

   sync_engine.py zeroes stale stock before each MERGE with
   "UPDATE Batches SET Stock = 0 WHERE StoreName = ? AND Stock > 0".
   The existing index IX_Batches_StoreName_ProductCode_BatchCode covers
   (StoreName, ProductCode, BatchCode) but not Stock, so that UPDATE scans
   every row for the store to find the ones with Stock > 0 instead of
   seeking -- the likely cause of multi-minute Batches sync steps on the
   shared SQL Server Express instance (1GB buffer-pool cap).

   Target database: OrderNMC (central, SQL Server 2014 Express). Also apply
   to OrderSMS / OrderSuccess if Batches exists there.
   Idempotent -- safe to run more than once. Run during a maintenance
   window: building this index takes a table-level lock for the duration
   on Express edition (no ONLINE=ON).
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_Batches_StoreName_Stock' AND object_id = OBJECT_ID('Batches')
)
    CREATE INDEX IX_Batches_StoreName_Stock
        ON Batches (StoreName, Stock)
        INCLUDE (ProductCode, BatchCode);
GO
