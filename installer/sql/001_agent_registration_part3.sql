SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Agent_Enable
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_Enable', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_Enable;
GO

CREATE PROCEDURE dbo.sp_Agent_Enable
(
    @agent_id BIGINT
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
        THROW 59201, 'Agent not found.', 1;

    UPDATE dbo.store_agent_registry
    SET
        is_active = 1,
        connection_status = 'ENABLED'
    WHERE agent_id = @agent_id;

    UPDATE s
    SET
        connection_status = 'ENABLED',
        updated_at = GETDATE()
    FROM dbo.stores s
    INNER JOIN dbo.store_agent_registry ar
        ON s.store_id = ar.store_id
    WHERE ar.agent_id = @agent_id;

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

/* ============================================================
   sp_Agent_Disable
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_Disable', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_Disable;
GO

CREATE PROCEDURE dbo.sp_Agent_Disable
(
    @agent_id BIGINT
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
        THROW 59202, 'Agent not found.', 1;

    UPDATE dbo.store_agent_registry
    SET
        is_active = 0,
        connection_status = 'DISABLED'
    WHERE agent_id = @agent_id;

    UPDATE s
    SET
        connection_status = 'DISABLED',
        updated_at = GETDATE()
    FROM dbo.stores s
    INNER JOIN dbo.store_agent_registry ar
        ON s.store_id = ar.store_id
    WHERE ar.agent_id = @agent_id;

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

/* ============================================================
   sp_Agent_CheckVersion
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_CheckVersion', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_CheckVersion;
GO

CREATE PROCEDURE dbo.sp_Agent_CheckVersion
(
    @store_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @current_version VARCHAR(50);

    SELECT
        @current_version = agent_version
    FROM dbo.store_agent_registry
    WHERE store_id = @store_id
      AND is_active = 1;

    SELECT TOP 1
        av.version_no AS latest_version,
        av.release_date,
        av.release_notes,
        @current_version AS installed_version,

        CASE
            WHEN @current_version = av.version_no
                THEN CAST(0 AS BIT)
            ELSE CAST(1 AS BIT)
        END AS update_available
    FROM dbo.agent_version_catalog av
    WHERE av.is_active = 1
    ORDER BY
        av.release_date DESC,
        av.version_id DESC;
END;
GO

/* ============================================================
   sp_Agent_GetStatus
   ============================================================ */

IF OBJECT_ID('dbo.sp_Agent_GetStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Agent_GetStatus;
GO

CREATE PROCEDURE dbo.sp_Agent_GetStatus
(
    @store_id UNIQUEIDENTIFIER
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

        ar.is_active,

        CASE
            WHEN ar.last_heartbeat IS NULL
                THEN 'UNKNOWN'

            WHEN DATEDIFF(MINUTE, ar.last_heartbeat, GETDATE()) <= 5
                THEN 'ONLINE'

            WHEN DATEDIFF(MINUTE, ar.last_heartbeat, GETDATE()) <= 30
                THEN 'WARNING'

            ELSE 'OFFLINE'
        END AS heartbeat_status,

        DATEDIFF(MINUTE, ar.last_heartbeat, GETDATE())
            AS minutes_since_last_heartbeat,

        (
            SELECT TOP 1
                av.version_no
            FROM dbo.agent_version_catalog av
            WHERE av.is_active = 1
            ORDER BY
                av.release_date DESC,
                av.version_id DESC
        ) AS latest_available_version

    FROM dbo.store_agent_registry ar
    INNER JOIN dbo.tenants t
        ON ar.tenant_id = t.tenant_id
    INNER JOIN dbo.stores s
        ON ar.store_id = s.store_id
    WHERE ar.store_id = @store_id;
END;
GO