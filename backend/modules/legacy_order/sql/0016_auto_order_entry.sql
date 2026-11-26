-- Automated Order Entry (PM submit -> random-delay auto process) + per-store
-- WhatsApp message-type settings. Applied on demand by auto_order_entry._ensure_schema.
-- SQL Server 2014: no CREATE OR ALTER / DROP IF EXISTS.

-- One row per store: whether a PM's Order Entry submit (last bill + GRN) is
-- queued for an unattended random-delay auto-process instead of running
-- immediately, and whether this store is allowed to actually send WhatsApp
-- (ProductionMode = 0 means every gated message is logged, never sent).
IF OBJECT_ID(N'dbo.StoreOrderAutomation', N'U') IS NULL
CREATE TABLE dbo.StoreOrderAutomation (
    StoreName              NVARCHAR(50)  NOT NULL CONSTRAINT PK_StoreOrderAutomation PRIMARY KEY,
    AutomatedOrderEnabled  BIT           NOT NULL CONSTRAINT DF_StoreOrderAutomation_AutoEnabled DEFAULT 0,
    ProductionMode         BIT           NOT NULL CONSTRAINT DF_StoreOrderAutomation_ProdMode DEFAULT 0,
    MinDelaySeconds        INT           NOT NULL CONSTRAINT DF_StoreOrderAutomation_MinDelay DEFAULT 60,
    MaxDelaySeconds        INT           NOT NULL CONSTRAINT DF_StoreOrderAutomation_MaxDelay DEFAULT 420,
    UpdatedAt              DATETIME      NOT NULL CONSTRAINT DF_StoreOrderAutomation_UpdatedAt DEFAULT GETDATE(),
    UpdatedBy              NVARCHAR(100) NULL
);
GO

-- One row per store + message type. TargetsJson is the same shape as
-- SupplierWhatsAppContact.TargetsJson (one group, or one-or-more contacts).
IF OBJECT_ID(N'dbo.StoreMessageSettings', N'U') IS NULL
CREATE TABLE dbo.StoreMessageSettings (
    StoreName     NVARCHAR(50)   NOT NULL,
    MessageType   NVARCHAR(40)   NOT NULL,
    Enabled       BIT            NOT NULL CONSTRAINT DF_StoreMessageSettings_Enabled DEFAULT 0,
    TargetsJson   NVARCHAR(MAX)  NULL,
    UpdatedAt     DATETIME       NOT NULL CONSTRAINT DF_StoreMessageSettings_UpdatedAt DEFAULT GETDATE(),
    UpdatedBy     NVARCHAR(100)  NULL,
    CONSTRAINT PK_StoreMessageSettings PRIMARY KEY (StoreName, MessageType)
);
GO

-- Pending/finished auto-process queue, one row per PM submit that was queued
-- (not an in-memory job -- a backend restart during the wait must not lose
-- the operator's submitted bill/GRN or silently never process the order).
IF OBJECT_ID(N'dbo.StoreAutoOrderQueue', N'U') IS NULL
CREATE TABLE dbo.StoreAutoOrderQueue (
    Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_StoreAutoOrderQueue PRIMARY KEY,
    StoreName     NVARCHAR(50)   NOT NULL,
    LastBill      NVARCHAR(50)   NULL,
    LastGrn       NVARCHAR(50)   NULL,
    OrderType     NVARCHAR(10)   NOT NULL CONSTRAINT DF_StoreAutoOrderQueue_OrderType DEFAULT 'REGULAR',
    Confirmed     BIT            NOT NULL CONSTRAINT DF_StoreAutoOrderQueue_Confirmed DEFAULT 0,
    Status        NVARCHAR(20)   NOT NULL CONSTRAINT DF_StoreAutoOrderQueue_Status DEFAULT 'PENDING',
    QueuedAt      DATETIME       NOT NULL CONSTRAINT DF_StoreAutoOrderQueue_QueuedAt DEFAULT GETDATE(),
    RunAt         DATETIME       NOT NULL,
    StartedAt     DATETIME       NULL,
    FinishedAt    DATETIME       NULL,
    JobId         NVARCHAR(64)   NULL,
    Error         NVARCHAR(MAX)  NULL,
    QueuedBy      NVARCHAR(100)  NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_StoreAutoOrderQueue_Store' AND object_id = OBJECT_ID(N'dbo.StoreAutoOrderQueue'))
CREATE INDEX IX_StoreAutoOrderQueue_Store ON dbo.StoreAutoOrderQueue (StoreName, Status, RunAt);
GO
