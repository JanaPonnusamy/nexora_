/* Legacy Order -- skip rules (same 3 modes as the UniNex/NEXORA platform's
   procurement skip, frontend/src/components/procurement/skipModes.ts).

   Target database: OrderNMC (central). Idempotent -- also applied at runtime
   by repository._ensure_skip_schema, so a fresh install needs no manual step.

     current_refresh   -- skip on THIS order only (never carried forward).
     until_next_sales  -- carried into every newly generated order until the
     until_next_demand    product makes a real sale after the skip
                          (SeriesTransID = 1, TransactionValidity = 0,
                          TransactionDate > SkippedAt) -- the same signal the
                          platform's carry_forward_skips uses for both modes.

   OrderManagement / OrderManagementBackup: the line's skip (mode + when + who).
   The two columns sets MUST stay in the same order on both tables -- the
   order process copies with a positional INSERT ... SELECT *.

   OrderProductSkip: the durable, store+product skip that survives order
   regeneration (one ACTIVE row per store+product; cleared rows are history).
*/

IF COL_LENGTH('OrderManagement', 'SkipReason') IS NULL
    ALTER TABLE OrderManagement ADD SkipReason VARCHAR(30) NULL, SkippedAt DATETIME NULL, SkippedBy NVARCHAR(100) NULL;
GO

IF COL_LENGTH('OrderManagementBackup', 'SkipReason') IS NULL
    ALTER TABLE OrderManagementBackup ADD SkipReason VARCHAR(30) NULL, SkippedAt DATETIME NULL, SkippedBy NVARCHAR(100) NULL;
GO

IF OBJECT_ID('dbo.OrderProductSkip', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.OrderProductSkip
    (
        SkipId      INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        StoreName   NVARCHAR(50)  NOT NULL,
        ProductCode FLOAT         NOT NULL,
        SkipReason  VARCHAR(30)   NOT NULL,
        OrderId     BIGINT        NULL,
        SkippedAt   DATETIME      NOT NULL CONSTRAINT DF_OrderProductSkip_SkippedAt DEFAULT GETDATE(),
        SkippedBy   NVARCHAR(100) NULL,
        ClearedAt   DATETIME      NULL,
        ClearedBy   NVARCHAR(100) NULL,
        ClearReason VARCHAR(30)   NULL   /* sale | manual | replaced */
    );
    CREATE UNIQUE INDEX UX_OrderProductSkip_Active
        ON dbo.OrderProductSkip (StoreName, ProductCode) WHERE ClearedAt IS NULL;
END
GO
