-- Supplier-wise WhatsApp targets + auto-send log (Procurement workspace,
-- store-level WhatsApp). Applied on demand by supplier_whatsapp._ensure_schema.
-- SQL Server 2014: no CREATE OR ALTER / DROP IF EXISTS.

-- One row per store + (unified) supplier code. TargetsJson is either ONE
-- group or one-or-more contacts: [{"name": "...", "kind": "group"|"contact"}].
IF OBJECT_ID(N'dbo.SupplierWhatsAppContact', N'U') IS NULL
CREATE TABLE dbo.SupplierWhatsAppContact (
    StoreName     NVARCHAR(50)   NOT NULL,
    SupplierCode  NVARCHAR(200)  NOT NULL,
    SupplierName  NVARCHAR(200)  NULL,
    TargetsJson   NVARCHAR(MAX)  NOT NULL,
    AutoSend      BIT            NOT NULL CONSTRAINT DF_SupplierWhatsAppContact_AutoSend DEFAULT 0,
    BatchSize     INT            NOT NULL CONSTRAINT DF_SupplierWhatsAppContact_BatchSize DEFAULT 20,
    SendFormat    NVARCHAR(10)   NOT NULL CONSTRAINT DF_SupplierWhatsAppContact_SendFormat DEFAULT 'image',
    BillDays      INT            NOT NULL CONSTRAINT DF_SupplierWhatsAppContact_BillDays DEFAULT 2,
    UpdatedAt     DATETIME       NOT NULL CONSTRAINT DF_SupplierWhatsAppContact_UpdatedAt DEFAULT GETDATE(),
    UpdatedBy     NVARCHAR(100)  NULL,
    CONSTRAINT PK_SupplierWhatsAppContact PRIMARY KEY (StoreName, SupplierCode)
);
GO

-- Every product the auto-send already posted to a supplier for an order, so
-- the next batch only carries what is new. Kind: 'batch' | 'final'.
IF OBJECT_ID(N'dbo.SupplierWhatsAppSent', N'U') IS NULL
CREATE TABLE dbo.SupplierWhatsAppSent (
    Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_SupplierWhatsAppSent PRIMARY KEY,
    StoreName     NVARCHAR(50)   NOT NULL,
    OrderId       BIGINT         NOT NULL,
    SupplierCode  NVARCHAR(200)  NOT NULL,
    ProductCode   NVARCHAR(50)   NOT NULL,
    Kind          NVARCHAR(10)   NOT NULL,
    BatchNo       INT            NOT NULL,
    SentAt        DATETIME       NOT NULL CONSTRAINT DF_SupplierWhatsAppSent_SentAt DEFAULT GETDATE(),
    SentBy        NVARCHAR(100)  NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_SupplierWhatsAppSent_Order' AND object_id = OBJECT_ID(N'dbo.SupplierWhatsAppSent'))
CREATE INDEX IX_SupplierWhatsAppSent_Order ON dbo.SupplierWhatsAppSent (StoreName, OrderId, SupplierCode) INCLUDE (ProductCode, Kind, BatchNo);
GO
