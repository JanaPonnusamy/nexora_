SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Store_Create
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_Create', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_Create;
GO

CREATE PROCEDURE dbo.sp_Store_Create
(
    @tenant_id UNIQUEIDENTIFIER,
    @store_code VARCHAR(50),
    @store_name VARCHAR(200),
    @server_name VARCHAR(500) = NULL,
    @database_name VARCHAR(200) = NULL,
    @username VARCHAR(200) = NULL,
    @password_encrypted VARBINARY(MAX) = NULL,
    @connection_type VARCHAR(50) = NULL,
    @branch_codes VARCHAR(MAX) = NULL
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
        THROW 51001, 'Invalid tenant.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE tenant_id = @tenant_id
          AND store_code = @store_code
    )
        THROW 51002, 'Store code already exists within tenant.', 1;

    DECLARE @store_id UNIQUEIDENTIFIER = NEWID();

    INSERT INTO dbo.stores
    (
        store_id,
        tenant_id,
        store_code,
        store_name,
        server_name,
        database_name,
        username,
        password_encrypted,
        connection_type,
        branch_codes,
        connection_status,
        is_active,
        created_at
    )
    VALUES
    (
        @store_id,
        @tenant_id,
        @store_code,
        @store_name,
        @server_name,
        @database_name,
        @username,
        @password_encrypted,
        @connection_type,
        @branch_codes,
        'NOT_TESTED',
        1,
        GETDATE()
    );

    SELECT *
    FROM dbo.stores
    WHERE store_id = @store_id;
END;
GO

/* ============================================================
   sp_Store_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_Update;
GO

CREATE PROCEDURE dbo.sp_Store_Update
(
    @store_id UNIQUEIDENTIFIER,
    @store_code VARCHAR(50),
    @store_name VARCHAR(200),
    @server_name VARCHAR(500) = NULL,
    @database_name VARCHAR(200) = NULL,
    @username VARCHAR(200) = NULL,
    @password_encrypted VARBINARY(MAX) = NULL,
    @connection_type VARCHAR(50) = NULL,
    @branch_codes VARCHAR(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @tenant_id UNIQUEIDENTIFIER;

    SELECT
        @tenant_id = tenant_id
    FROM dbo.stores
    WHERE store_id = @store_id;

    IF @tenant_id IS NULL
        THROW 51003, 'Store not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE tenant_id = @tenant_id
          AND store_code = @store_code
          AND store_id <> @store_id
    )
        THROW 51004, 'Store code already exists within tenant.', 1;

    UPDATE dbo.stores
    SET
        store_code = @store_code,
        store_name = @store_name,
        server_name = @server_name,
        database_name = @database_name,
        username = @username,
        password_encrypted = @password_encrypted,
        connection_type = @connection_type,
        branch_codes = @branch_codes,
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    SELECT *
    FROM dbo.stores
    WHERE store_id = @store_id;
END;
GO

/* ============================================================
   sp_Store_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_Get;
GO

CREATE PROCEDURE dbo.sp_Store_Get
(
    @store_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        s.*,
        t.tenant_code,
        t.tenant_name
    FROM dbo.stores s
    INNER JOIN dbo.tenants t
        ON s.tenant_id = t.tenant_id
    WHERE s.store_id = @store_id;
END;
GO

/* ============================================================
   sp_Store_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_List;
GO

CREATE PROCEDURE dbo.sp_Store_List
(
    @tenant_id UNIQUEIDENTIFIER = NULL,
    @is_active BIT = NULL,
    @search VARCHAR(200) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        s.store_id,
        s.tenant_id,
        t.tenant_code,
        t.tenant_name,
        s.store_code,
        s.store_name,
        s.connection_type,
        s.connection_status,
        s.last_sync_status,
        s.last_sync_time,
        s.last_seen,
        s.is_active,
        s.created_at
    FROM dbo.stores s
    INNER JOIN dbo.tenants t
        ON s.tenant_id = t.tenant_id
    WHERE
        (
            @tenant_id IS NULL
            OR s.tenant_id = @tenant_id
        )
        AND
        (
            @is_active IS NULL
            OR s.is_active = @is_active
        )
        AND
        (
            @search IS NULL
            OR s.store_code LIKE '%' + @search + '%'
            OR s.store_name LIKE '%' + @search + '%'
            OR t.tenant_name LIKE '%' + @search + '%'
        )
    ORDER BY
        t.tenant_name,
        s.store_name;
END;
GO

/* ============================================================
   sp_Store_Activate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_Activate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_Activate;
GO

CREATE PROCEDURE dbo.sp_Store_Activate
(
    @store_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.stores
    SET
        is_active = 1,
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    SELECT *
    FROM dbo.stores
    WHERE store_id = @store_id;
END;
GO

/* ============================================================
   sp_Store_Deactivate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_Deactivate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_Deactivate;
GO

CREATE PROCEDURE dbo.sp_Store_Deactivate
(
    @store_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.stores
    SET
        is_active = 0,
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    SELECT *
    FROM dbo.stores
    WHERE store_id = @store_id;
END;
GO

/* ============================================================
   sp_Store_TestConnection
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_TestConnection', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_TestConnection;
GO

CREATE PROCEDURE dbo.sp_Store_TestConnection
(
    @store_id UNIQUEIDENTIFIER,
    @connection_status VARCHAR(50),
    @last_sync_status VARCHAR(50) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.stores
    SET
        connection_status = @connection_status,
        last_sync_status = ISNULL(@last_sync_status,last_sync_status),
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    SELECT
        store_id,
        store_code,
        store_name,
        connection_status,
        last_sync_status,
        updated_at
    FROM dbo.stores
    WHERE store_id = @store_id;
END;
GO

/* ============================================================
   sp_Store_HeartbeatUpdate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Store_HeartbeatUpdate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Store_HeartbeatUpdate;
GO

CREATE PROCEDURE dbo.sp_Store_HeartbeatUpdate
(
    @store_id UNIQUEIDENTIFIER,
    @heartbeat_ip VARCHAR(100),
    @connection_status VARCHAR(50),
    @last_sync_status VARCHAR(50) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.stores
    SET
        heartbeat_ip = @heartbeat_ip,
        last_seen = GETDATE(),
        connection_status = @connection_status,
        last_sync_status = ISNULL(@last_sync_status,last_sync_status),
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    SELECT
        store_id,
        store_code,
        store_name,
        heartbeat_ip,
        last_seen,
        connection_status,
        last_sync_status
    FROM dbo.stores
    WHERE store_id = @store_id;
END;
GO