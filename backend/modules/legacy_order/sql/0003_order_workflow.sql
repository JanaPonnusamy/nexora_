/* Legacy Order -- durable web workflow and line-level audit trail.

   Target database: OrderNMC (central, SQL Server 2014+).
   Idempotent: safe to run during deployment more than once.

   This does not alter the legacy OrderManagement layout. The VB.NET desktop
   client can continue reading and writing the same rows while Nexora records
   workflow/finalization state alongside them.
*/

IF OBJECT_ID('dbo.LegacyOrderWorkflow', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyOrderWorkflow (
        WorkflowId UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT DF_LegacyOrderWorkflow_Id DEFAULT NEWID(),
        StoreName NVARCHAR(100) NOT NULL,
        OrderId BIGINT NOT NULL,
        Status VARCHAR(24) NOT NULL
            CONSTRAINT DF_LegacyOrderWorkflow_Status DEFAULT 'DRAFT',
        StartedAt DATETIME2(0) NOT NULL
            CONSTRAINT DF_LegacyOrderWorkflow_StartedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(0) NOT NULL
            CONSTRAINT DF_LegacyOrderWorkflow_UpdatedAt DEFAULT SYSUTCDATETIME(),
        FinalizedAt DATETIME2(0) NULL,
        UpdatedBy NVARCHAR(128) NULL,
        Note NVARCHAR(500) NULL,
        CONSTRAINT PK_LegacyOrderWorkflow PRIMARY KEY (WorkflowId),
        CONSTRAINT UQ_LegacyOrderWorkflow_Store_Order UNIQUE (StoreName, OrderId),
        CONSTRAINT CK_LegacyOrderWorkflow_Status
            CHECK (Status IN ('DRAFT', 'QTY_REVIEW', 'SUPPLIER_ASSIGNMENT', 'READY', 'FINALIZED'))
    );
END;
GO

IF OBJECT_ID('dbo.LegacyOrderWorkflowAudit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyOrderWorkflowAudit (
        AuditId BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        StoreName NVARCHAR(100) NOT NULL,
        OrderId BIGINT NOT NULL,
        ProductCode BIGINT NULL,
        Action VARCHAR(40) NOT NULL,
        OldValue NVARCHAR(500) NULL,
        NewValue NVARCHAR(500) NULL,
        Actor NVARCHAR(128) NULL,
        CreatedAt DATETIME2(0) NOT NULL
            CONSTRAINT DF_LegacyOrderWorkflowAudit_CreatedAt DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_LegacyOrderWorkflowAudit_Store_Order_Created'
      AND object_id = OBJECT_ID('dbo.LegacyOrderWorkflowAudit')
)
    CREATE INDEX IX_LegacyOrderWorkflowAudit_Store_Order_Created
        ON dbo.LegacyOrderWorkflowAudit (StoreName, OrderId, CreatedAt DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_OrderManagement_Workflow_Readiness'
      AND object_id = OBJECT_ID('dbo.OrderManagement')
)
    CREATE INDEX IX_OrderManagement_Workflow_Readiness
        ON dbo.OrderManagement (StoreName, OrderId, Status, QtyCheck)
        INCLUDE (ProductCode, OrderQty, OrgOrderQty, PurchasePrice);
GO
