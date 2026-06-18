SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Agent_Heartbeat
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_Heartbeat', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_Heartbeat;
GO

CREATE PROCEDURE dbo.sp_Agent_Heartbeat
(
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,
    @ip_address VARCHAR(100) = NULL,
    @agent_version VARCHAR(50)
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.store_agent_registry
        WHERE tenant_id = @tenant_id
          AND store_id = @store_id
          AND is_active = 1
    )
        THROW 59101, 'Active agent registration not found.', 1;

    INSERT INTO dbo.agent_heartbeat_log
    (
        tenant_id,
        store_id,
        heartbeat_time,
        ip_address,
        agent_version
    )
    VALUES
    (
        @tenant_id,
        @store_id,
        GETDATE(),
        @ip_address,
        @agent_version
    );

    UPDATE dbo.store_agent_registry
    SET
        last_heartbeat = GETDATE(),
        connection_status = 'ONLINE',
        agent_version = @agent_version
    WHERE tenant_id = @tenant_id
      AND store_id = @store_id
      AND is_active = 1;

    UPDATE dbo.stores
    SET
        last_heartbeat = GETDATE(),
        last_seen = GETDATE(),
        connection_status = 'ONLINE',
        agent_version = @agent_version,
        updated_at = GETDATE()
    WHERE tenant_id = @tenant_id
      AND store_id = @store_id;

    SELECT
        agent_id,
        tenant_id,
        store_id,
        agent_version,
        last_heartbeat,
        connection_status
    FROM dbo.store_agent_registry
    WHERE tenant_id = @tenant_id
      AND store_id = @store_id
      AND is_active = 1;
END;
GO

/* ============================================================
   sp_Agent_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_Get;
GO

CREATE PROCEDURE dbo.sp_Agent_Get
(
    @agent_id BIGINT
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ar.agent_id,
        ar.tenant_id,
        t.tenant_code,
        t.tenant_name,

        ar.store_id,
        s.store_code,
        s.store_name,

        ar.agent_version,
        ar.connection_type,
        ar.installed_at,
        ar.last_heartbeat,
        ar.connection_status,
        ar.is_active

    FROM dbo.store_agent_registry ar
    INNER JOIN dbo.tenants t
        ON ar.tenant_id = t.tenant_id
    INNER JOIN dbo.stores s
        ON ar.store_id = s.store_id
    WHERE ar.agent_id = @agent_id;
END;
GO

/* ============================================================
   sp_Agent_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_List;
GO

CREATE PROCEDURE dbo.sp_Agent_List
(
    @tenant_id UNIQUEIDENTIFIER = NULL,
    @store_id UNIQUEIDENTIFIER = NULL,
    @is_active BIT = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ar.agent_id,

        ar.tenant_id,
        t.tenant_code,
        t.tenant_name,

        ar.store_id,
        s.store_code,
        s.store_name,

        ar.agent_version,
        ar.connection_type,

        ar.installed_at,
        ar.last_heartbeat,

        ar.connection_status,

        CASE
            WHEN ar.last_heartbeat IS NULL
                THEN 'UNKNOWN'

            WHEN DATEDIFF(MINUTE, ar.last_heartbeat, GETDATE()) <= 5
                THEN 'ONLINE'

            WHEN DATEDIFF(MINUTE, ar.last_heartbeat, GETDATE()) <= 30
                THEN 'WARNING'

            ELSE 'OFFLINE'
        END AS heartbeat_status,

        ar.is_active

    FROM dbo.store_agent_registry ar
    INNER JOIN dbo.tenants t
        ON ar.tenant_id = t.tenant_id
    INNER JOIN dbo.stores s
        ON ar.store_id = s.store_id

    WHERE
        (
            @tenant_id IS NULL
            OR ar.tenant_id = @tenant_id
        )
        AND
        (
            @store_id IS NULL
            OR ar.store_id = @store_id
        )
        AND
        (
            @is_active IS NULL
            OR ar.is_active = @is_active
        )

    ORDER BY
        t.tenant_name,
        s.store_name;
END;
GO