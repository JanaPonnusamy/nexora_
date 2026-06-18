SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncConfig_Create
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncConfig_Create', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncConfig_Create;
GO

CREATE PROCEDURE dbo.sp_SyncConfig_Create
(
    @tenant_id UNIQUEIDENTIFIER,
    @config_name VARCHAR(100),
    @created_by UNIQUEIDENTIFIER
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
        THROW 60001, 'Tenant not found.', 1;

    IF NULLIF(LTRIM(RTRIM(@config_name)), '') IS NULL
        THROW 60002, 'Configuration name is required.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_configuration
        WHERE tenant_id = @tenant_id
          AND config_name = @config_name
    )
        THROW 60003, 'Configuration already exists.', 1;

    INSERT INTO dbo.sync_configuration
    (
        tenant_id,
        config_name,
        is_active,
        created_at,
        created_by
    )
    VALUES
    (
        @tenant_id,
        @config_name,
        1,
        GETDATE(),
        @created_by
    );

    SELECT *
    FROM dbo.sync_configuration
    WHERE config_id = SCOPE_IDENTITY();
END;
GO

/* ============================================================
   sp_SyncConfig_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncConfig_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncConfig_Update;
GO

CREATE PROCEDURE dbo.sp_SyncConfig_Update
(
    @config_id BIGINT,
    @config_name VARCHAR(100),
    @is_active BIT,
    @updated_by UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.sync_configuration
        WHERE config_id = @config_id
    )
        THROW 60004, 'Configuration not found.', 1;

    DECLARE @tenant_id UNIQUEIDENTIFIER;

    SELECT
        @tenant_id = tenant_id
    FROM dbo.sync_configuration
    WHERE config_id = @config_id;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_configuration
        WHERE tenant_id = @tenant_id
          AND config_name = @config_name
          AND config_id <> @config_id
    )
        THROW 60005, 'Configuration name already exists.', 1;

    UPDATE dbo.sync_configuration
    SET
        config_name = @config_name,
        is_active = @is_active,
        updated_at = GETDATE(),
        updated_by = @updated_by
    WHERE config_id = @config_id;

    SELECT *
    FROM dbo.sync_configuration
    WHERE config_id = @config_id;
END;
GO

/* ============================================================
   sp_SyncConfig_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncConfig_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncConfig_Get;
GO

CREATE PROCEDURE dbo.sp_SyncConfig_Get
(
    @config_id BIGINT
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        sc.config_id,
        sc.tenant_id,
        t.tenant_code,
        t.tenant_name,
        sc.config_name,
        sc.is_active,
        sc.created_at,
        sc.created_by,
        sc.updated_at,
        sc.updated_by
    FROM dbo.sync_configuration sc
    INNER JOIN dbo.tenants t
        ON sc.tenant_id = t.tenant_id
    WHERE sc.config_id = @config_id;
END;
GO

/* ============================================================
   sp_SyncConfig_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncConfig_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncConfig_List;
GO

CREATE PROCEDURE dbo.sp_SyncConfig_List
(
    @tenant_id UNIQUEIDENTIFIER = NULL,
    @is_active BIT = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        sc.config_id,
        sc.tenant_id,
        t.tenant_code,
        t.tenant_name,
        sc.config_name,
        sc.is_active,
        sc.created_at,
        sc.updated_at
    FROM dbo.sync_configuration sc
    INNER JOIN dbo.tenants t
        ON sc.tenant_id = t.tenant_id
    WHERE
        (
            @tenant_id IS NULL
            OR sc.tenant_id = @tenant_id
        )
        AND
        (
            @is_active IS NULL
            OR sc.is_active = @is_active
        )
    ORDER BY
        t.tenant_name,
        sc.config_name;
END;
GO