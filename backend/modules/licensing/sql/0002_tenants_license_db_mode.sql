-- Per-tenant choice of where licensing/usage data (tenant_licenses,
-- tenant_license_audit, tenant_usage_status) is stored: the shared
-- NEXORA_PLATFORM database (default) or a separate dedicated database for
-- tenants HO wants isolated. dbo.tenants itself ALWAYS stays in the shared
-- platform DB - it is the routing table these columns live on.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.tenants') AND name = 'license_db_mode'
)
BEGIN
    ALTER TABLE dbo.tenants ADD license_db_mode NVARCHAR(20) NOT NULL
        CONSTRAINT DF_tenants_license_db_mode DEFAULT ('SHARED'); -- SHARED | DEDICATED
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.tenants') AND name = 'license_db_server'
)
BEGIN ALTER TABLE dbo.tenants ADD license_db_server NVARCHAR(200) NULL; END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.tenants') AND name = 'license_db_name'
)
BEGIN ALTER TABLE dbo.tenants ADD license_db_name NVARCHAR(200) NULL; END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.tenants') AND name = 'license_db_username'
)
BEGIN ALTER TABLE dbo.tenants ADD license_db_username NVARCHAR(200) NULL; END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.tenants') AND name = 'license_db_password_encrypted'
)
BEGIN ALTER TABLE dbo.tenants ADD license_db_password_encrypted VARBINARY(500) NULL; END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.tenants') AND name = 'license_db_driver'
)
BEGIN ALTER TABLE dbo.tenants ADD license_db_driver NVARCHAR(100) NULL; END;
