/* Legacy Order -- durable pending-export processing lock.

   Target database: OrderNMC (central, SQL Server 2014 Express).
   Idempotent -- safe to run more than once.

   Problem: Order Process (service.start_order_process) deletes and
   regenerates every OrderManagement row for a store (order_process.
   insert_data_into_destination). If a previously generated order still has
   lines sitting at Status = 0 (not yet assigned to a supplier, so never
   exported -- see order_export.export_order, which assigns Status 0->1 and
   exports in the same call), running Process again silently discards those
   unexported lines. The only existing guard (service._running_job_kind) is
   an in-memory, per-process "is a job already running" check -- it says
   nothing about whether the PREVIOUS order still has unexported quantities,
   and it is wiped by a backend restart.

   Fix: a durable, store-scoped lock, independent of the in-memory job dict.
   One row per store (StoreName is the PK -- Process always acts on "the
   latest order" for that store, so a second in-flight order for the same
   store is never a valid state to protect against separately). The lock
   remembers which OrderId triggered it purely for display/audit; it is not
   part of the lookup key, because the whole point is to survive the next
   regeneration attempt (which would otherwise change the "latest" OrderId
   before the lock could ever be read back).

   Rollback: DROP TABLE; see bottom of this file.
*/

IF OBJECT_ID('dbo.LegacyOrderProcessingLock', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyOrderProcessingLock (
        StoreName NVARCHAR(100) NOT NULL PRIMARY KEY,
        OrderId BIGINT NOT NULL,
        Reason NVARCHAR(500) NOT NULL,
        LockedAt DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
        UnlockedAt DATETIME2(0) NULL,
        UnlockedBy NVARCHAR(128) NULL,
        UnlockReason NVARCHAR(500) NULL
    );
END;
GO

/* Rollback (run manually if reverting):
   DROP TABLE dbo.LegacyOrderProcessingLock;
*/
