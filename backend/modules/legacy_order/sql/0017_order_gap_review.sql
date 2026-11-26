-- Order Gap Review: a PM's reconciliation screen for the gap since a
-- store's last placed order (which may span multiple days, e.g. reviewing
-- Saturday's order on Monday). Applied on demand by repository._ensure_gap_review_schema.
-- SQL Server 2014: no CREATE OR ALTER / DROP IF EXISTS.

-- Carries forward products the PM has explicitly flagged as "ordered but
-- never arrived" so the next review still reminds them, even once the
-- underlying OrderManagementBackup window has moved on. A row is cleared
-- either automatically (a later GRN for that product arrives) or manually
-- by the PM dismissing it.
IF OBJECT_ID(N'dbo.StorePendingOrderItems', N'U') IS NULL
CREATE TABLE dbo.StorePendingOrderItems (
    Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_StorePendingOrderItems PRIMARY KEY,
    StoreName     NVARCHAR(50)   NOT NULL,
    ProductCode   INT            NOT NULL,
    ProductName   NVARCHAR(200)  NULL,
    OrderId       BIGINT         NULL,
    Qty           FLOAT          NULL,
    FlaggedAt     DATETIME       NOT NULL CONSTRAINT DF_StorePendingOrderItems_FlaggedAt DEFAULT GETDATE(),
    FlaggedBy     NVARCHAR(100)  NULL,
    ClearedAt     DATETIME       NULL,
    Note          NVARCHAR(500)  NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_StorePendingOrderItems_Store' AND object_id = OBJECT_ID(N'dbo.StorePendingOrderItems'))
CREATE INDEX IX_StorePendingOrderItems_Store ON dbo.StorePendingOrderItems (StoreName, ClearedAt);
GO

-- The PM's "Review done" for an order (Order Entry step 1): the PM Order
-- Entry submit is refused until the store's CURRENT order (the one in
-- OrderManagement, i.e. the last one placed) has a row here.
IF OBJECT_ID(N'dbo.StoreGapReviewLog', N'U') IS NULL
CREATE TABLE dbo.StoreGapReviewLog (
    Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_StoreGapReviewLog PRIMARY KEY,
    StoreName     NVARCHAR(50)   NOT NULL,
    OrderId       BIGINT         NOT NULL,
    ReviewedAt    DATETIME       NOT NULL CONSTRAINT DF_StoreGapReviewLog_ReviewedAt DEFAULT GETDATE(),
    ReviewedBy    NVARCHAR(100)  NULL,
    NotReceived   INT            NULL,
    PendingCount  INT            NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_StoreGapReviewLog_Store' AND object_id = OBJECT_ID(N'dbo.StoreGapReviewLog'))
CREATE INDEX IX_StoreGapReviewLog_Store ON dbo.StoreGapReviewLog (StoreName, OrderId);
GO
