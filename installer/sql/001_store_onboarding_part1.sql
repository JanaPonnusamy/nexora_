SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   STORE ONBOARDING TABLES
   ============================================================ */

IF OBJECT_ID('dbo.store_onboarding_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.store_onboarding_log
    (
        onboarding_id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NULL,

        onboarding_status VARCHAR(50) NOT NULL,

        started_by UNIQUEIDENTIFIER NOT NULL,

        started_at DATETIME NOT NULL,

        completed_at DATETIME NULL,

        remarks NVARCHAR(MAX) NULL
    );
END;
GO

IF OBJECT_ID('dbo.store_connection_test_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.store_connection_test_log
    (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NULL,

        server_name VARCHAR(500) NULL,

        database_name VARCHAR(200) NULL,

        test_status VARCHAR(50) NOT NULL,

        test_message NVARCHAR(MAX) NULL,

        tested_by UNIQUEIDENTIFIER NOT NULL,

        tested_at DATETIME NOT NULL
    );
END;
GO

IF OBJECT_ID('dbo.store_agent_registry', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.store_agent_registry
    (
        agent_id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NOT NULL,

        agent_version VARCHAR(50) NOT NULL,

        connection_type VARCHAR(50) NOT NULL,

        installed_at DATETIME NOT NULL,

        last_heartbeat DATETIME NULL,

        connection_status VARCHAR(50) NULL,

        is_active BIT NOT NULL
    );
END;
GO

IF OBJECT_ID('dbo.store_sync_settings', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.store_sync_settings
    (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NOT NULL,

        sync_enabled BIT NOT NULL,

        initial_sync_type VARCHAR(20) NOT NULL,

        schedule_enabled BIT NOT NULL,

        created_at DATETIME NOT NULL
    );
END;
GO

/* ============================================================
   INDEXES
   ============================================================ */

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_store_onboarding_log_tenant'
)
BEGIN
    CREATE INDEX IX_store_onboarding_log_tenant
    ON dbo.store_onboarding_log(tenant_id);
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_store_onboarding_log_store'
)
BEGIN
    CREATE INDEX IX_store_onboarding_log_store
    ON dbo.store_onboarding_log(store_id);
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_store_agent_registry_store'
)
BEGIN
    CREATE INDEX IX_store_agent_registry_store
    ON dbo.store_agent_registry(store_id);
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_store_sync_settings_store'
)
BEGIN
    CREATE INDEX IX_store_sync_settings_store
    ON dbo.store_sync_settings(store_id);
END;
GO

/* ============================================================
   sp_StoreOnboarding_Start
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_Start', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_Start;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_Start
(
    @tenant_id UNIQUEIDENTIFIER,
    @started_by UNIQUEIDENTIFIER,
    @remarks NVARCHAR(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_id = @tenant_id
          AND is_active = 1
    )
    BEGIN
        THROW 58001, 'Tenant not found or inactive.', 1;
    END;

    DECLARE @onboarding_id BIGINT;

    INSERT INTO dbo.store_onboarding_log
    (
        tenant_id,
        store_id,
        onboarding_status,
        started_by,
        started_at,
        completed_at,
        remarks
    )
    VALUES
    (
        @tenant_id,
        NULL,
        'STARTED',
        @started_by,
        GETDATE(),
        NULL,
        @remarks
    );

    SET @onboarding_id = SCOPE_IDENTITY();

    SELECT
        onboarding_id,
        tenant_id,
        store_id,
        onboarding_status,
        started_by,
        started_at,
        completed_at,
        remarks
    FROM dbo.store_onboarding_log
    WHERE onboarding_id = @onboarding_id;
END;
GO