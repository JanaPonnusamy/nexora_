SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_RegisterAgent
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_RegisterAgent', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_RegisterAgent;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_RegisterAgent
(
    @onboarding_id BIGINT,
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,

    @agent_version VARCHAR(50),

    @connection_type VARCHAR(50),

    @connection_status VARCHAR(50) = 'ACTIVE'
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.store_onboarding_log
        WHERE onboarding_id = @onboarding_id
    )
    BEGIN
        THROW 58301, 'Invalid onboarding session.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND tenant_id = @tenant_id
    )
    BEGIN
        THROW 58302, 'Store not found.', 1;
    END;

    IF NULLIF(LTRIM(RTRIM(@agent_version)), '') IS NULL
    BEGIN
        THROW 58303, 'Agent Version is required.', 1;
    END;

    IF @connection_type NOT IN ('LAN','VPN','Public IP')
    BEGIN
        THROW 58304, 'Invalid Connection Type.', 1;
    END;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.store_agent_registry
        WHERE store_id = @store_id
          AND is_active = 1
    )
    BEGIN

        UPDATE dbo.store_agent_registry
        SET
            agent_version = @agent_version,
            connection_type = @connection_type,
            installed_at = GETDATE(),
            last_heartbeat = GETDATE(),
            connection_status = @connection_status,
            is_active = 1
        WHERE store_id = @store_id;

    END
    ELSE
    BEGIN

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
            @connection_status,
            1
        );

    END;

    UPDATE dbo.stores
    SET
        agent_version = @agent_version,
        agent_installed_at = GETDATE(),
        last_heartbeat = GETDATE(),
        connection_type = @connection_type,
        connection_status = @connection_status,
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    UPDATE dbo.store_onboarding_log
    SET
        onboarding_status = 'AGENT_REGISTERED'
    WHERE onboarding_id = @onboarding_id;

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
    WHERE store_id = @store_id
      AND is_active = 1;
END;
GO