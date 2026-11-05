-- Supplier ordering portals for the Procurement workspace's Sites panel.
-- Applied on demand by supplier_portal._ensure_schema.
-- SQL Server 2014: no CREATE OR ALTER / DROP IF EXISTS.

-- SUPPLIER level: one row per portal, the same for every store. UserName +
-- PasswordEnc = the login all stores share unless a store saved its own.
-- PasswordEnc is Fernet-encrypted with the platform key (as dbo.stores).
IF OBJECT_ID(N'dbo.SupplierPortal', N'U') IS NULL
CREATE TABLE dbo.SupplierPortal (
    PortalId      INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_SupplierPortal PRIMARY KEY,
    PortalName    NVARCHAR(100)  NOT NULL,
    PortalUrl     NVARCHAR(1000) NOT NULL,
    UserName      NVARCHAR(200)  NULL,
    PasswordEnc   VARBINARY(MAX) NULL,
    AutoSubmit    BIT            NOT NULL CONSTRAINT DF_SupplierPortal_AutoSubmit DEFAULT 1,
    SortOrder     INT            NOT NULL CONSTRAINT DF_SupplierPortal_SortOrder DEFAULT 0,
    UpdatedAt     DATETIME       NOT NULL CONSTRAINT DF_SupplierPortal_UpdatedAt DEFAULT GETDATE(),
    UpdatedBy     NVARCHAR(100)  NULL
);
GO

-- STORE level: per store + portal, which of the store's suppliers orders
-- there (its UnifiedSupplierCODE -- branch codes differ per store, so the
-- link lives here, not on the portal) and the store's own login, which wins
-- over the supplier-level one. AutoSubmit NULL = as the portal.
IF OBJECT_ID(N'dbo.SupplierPortalStore', N'U') IS NULL
CREATE TABLE dbo.SupplierPortalStore (
    StoreName     NVARCHAR(50)   NOT NULL,
    PortalId      INT            NOT NULL CONSTRAINT FK_SupplierPortalStore_Portal
                                   REFERENCES dbo.SupplierPortal (PortalId) ON DELETE CASCADE,
    SupplierCode  NVARCHAR(200)  NULL,
    SupplierName  NVARCHAR(200)  NULL,
    UserName      NVARCHAR(200)  NULL,
    PasswordEnc   VARBINARY(MAX) NULL,
    AutoSubmit    BIT            NULL,
    UpdatedAt     DATETIME       NOT NULL CONSTRAINT DF_SupplierPortalStore_UpdatedAt DEFAULT GETDATE(),
    UpdatedBy     NVARCHAR(100)  NULL,
    CONSTRAINT PK_SupplierPortalStore PRIMARY KEY (StoreName, PortalId)
);
GO
