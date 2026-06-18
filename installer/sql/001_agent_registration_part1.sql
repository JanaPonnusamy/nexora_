SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Agent_Register
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_Register', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_Register;
GO

CREATE PROCEDURE dbo.sp_Agent_Register
(
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,
    @agent_version VARCHAR(50),
    @connection_type VARCHAR(50)
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
        THROW 59001, 'Tenant not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND tenant_id = @tenant_id
          AND is_active = 1
    )
        THROW 59002, 'Store not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.agent_version_catalog
        WHERE version_no = @agent_version
          AND is_active = 1
    )
        THROW 59003, 'Agent version not approved.', 1;

    IF @connection_type NOT IN ('LAN','VPN','Public IP')
        THROW 59004, 'Invalid connection type.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.store_agent_registry
        WHERE store_id = @store_id
          AND is_active = 1
    )
        THROW 59005, 'Agent already registered.', 1;

    INSERT INTO dbo.store_agent_registry
    (
        tenant_id,
        store_id,
        agent_version,
        connection_type,
        installed_at,
        last_heartbeat,
        connection_status,
        is_active
    )
    VALUES
    (
        @tenant_id,
        @store_id,
        @agent_version,
        @connection_type,
        GETDATE(),
        GETDATE(),
        'REGISTERED',
        1
    );

    UPDATE dbo.stores
    SET
        agent_version = @agent_version,
        agent_installed_at = GETDATE(),
        last_heartbeat = GETDATE(),
        connection_type = @connection_type,
        connection_status = 'REGISTERED',
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    SELECT
        agent_id,
        tenant_id,
        store_id,
        agent_version,
        connection_type,
        installed_at,
        last_heartbeat,
        connection_status,
        is_active
    FROM dbo.store_agent_registry
    WHERE agent_id = SCOPE_IDENTITY();
END;
GO

/* ============================================================
   sp_Agent_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_Update;
GO

CREATE PROCEDURE dbo.sp_Agent_Update
(
    @agent_id BIGINT,
    @agent_version VARCHAR(50),
    @connection_type VARCHAR(50),
    @connection_status VARCHAR(50)
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.store_agent_registry
        WHERE agent_id = @agent_id
    )
        THROW 59011, 'Agent not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.agent_version_catalog
        WHERE version_no = @agent_version
          AND is_active = 1
    )
        THROW 59012, 'Agent version not approved.', 1;

    IF @connection_type NOT IN ('LAN','VPN','Public IP')
        THROW 59013, 'Invalid connection type.', 1;

    UPDATE dbo.store_agent_registry
    SET
        agent_version = @agent_version,
        connection_type = @connection_type,
        connection_status = @connection_status
    WHERE agent_id = @agent_id;

    UPDATE s
    SET
        s.agent_version = r.agent_version,
        s.connection_type = r.connection_type,
        s.connection_status = r.connection_status,
        s.updated_at = GETDATE()
    FROM dbo.stores s
    INNER JOIN dbo.store_agent_registry r
        ON s.store_id = r.store_id
    WHERE r.agent_id = @agent_id;

    SELECT
        agent_id,
        tenant_id,
        store_id,
        agent_version,
        connection_type,
        installed_at,
        last_heartbeat,
        connection_status,
        is_active
    FROM dbo.store_agent_registry
    WHERE agent_id = @agent_id;
END;
GO