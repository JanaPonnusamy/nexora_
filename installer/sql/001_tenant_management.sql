SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   Tenant Management V1
   ============================================================ */

IF OBJECT_ID('dbo.sp_Tenant_Create', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Tenant_Create;
GO

CREATE PROCEDURE dbo.sp_Tenant_Create
(
    @tenant_code           VARCHAR(50),
    @tenant_abbreviation   VARCHAR(20),
    @tenant_name           VARCHAR(200),
    @platform_version      VARCHAR(20),
    @tenant_db_version     VARCHAR(20),
    @contact_name          VARCHAR(100) = NULL,
    @contact_email         VARCHAR(200) = NULL,
    @contact_phone         VARCHAR(50) = NULL,
    @created_by            UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@tenant_code)), '') IS NULL
        THROW 50001, 'tenant_code is required.', 1;

    IF NULLIF(LTRIM(RTRIM(@tenant_abbreviation)), '') IS NULL
        THROW 50002, 'tenant_abbreviation is required.', 1;

    IF NULLIF(LTRIM(RTRIM(@tenant_name)), '') IS NULL
        THROW 50003, 'tenant_name is required.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_code = @tenant_code
    )
        THROW 50004, 'tenant_code already exists.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_abbreviation = @tenant_abbreviation
    )
        THROW 50005, 'tenant_abbreviation already exists.', 1;

    DECLARE @tenant_id UNIQUEIDENTIFIER = NEWID();

    DECLARE @db_name VARCHAR(200);

    SET @db_name =
        'NEXORA_' +
        UPPER(REPLACE(@tenant_abbreviation, ' ', '_'));

    INSERT INTO dbo.tenants
    (
        tenant_id,
        tenant_code,
        tenant_abbreviation,
        tenant_name,
        db_name,
        platform_version,
        tenant_db_version,
        contact_name,
        contact_email,
        contact_phone,
        is_active,
        created_at,
        created_by
    )
    VALUES
    (
        @tenant_id,
        @tenant_code,
        @tenant_abbreviation,
        @tenant_name,
        @db_name,
        @platform_version,
        @tenant_db_version,
        @contact_name,
        @contact_email,
        @contact_phone,
        1,
        GETDATE(),
        @created_by
    );

    SELECT *
    FROM dbo.tenants
    WHERE tenant_id = @tenant_id;
END;
GO

/* ============================================================
   sp_Tenant_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_Tenant_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Tenant_Update;
GO

CREATE PROCEDURE dbo.sp_Tenant_Update
(
    @tenant_id             UNIQUEIDENTIFIER,
    @tenant_code           VARCHAR(50),
    @tenant_abbreviation   VARCHAR(20),
    @tenant_name           VARCHAR(200),
    @platform_version      VARCHAR(20),
    @tenant_db_version     VARCHAR(20),
    @contact_name          VARCHAR(100) = NULL,
    @contact_email         VARCHAR(200) = NULL,
    @contact_phone         VARCHAR(50) = NULL,
    @updated_by            UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_id = @tenant_id
    )
        THROW 50006, 'Tenant not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_code = @tenant_code
          AND tenant_id <> @tenant_id
    )
        THROW 50007, 'tenant_code already exists.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_abbreviation = @tenant_abbreviation
          AND tenant_id <> @tenant_id
    )
        THROW 50008, 'tenant_abbreviation already exists.', 1;

    UPDATE dbo.tenants
    SET
        tenant_code         = @tenant_code,
        tenant_abbreviation = @tenant_abbreviation,
        tenant_name         = @tenant_name,
        platform_version    = @platform_version,
        tenant_db_version   = @tenant_db_version,
        contact_name        = @contact_name,
        contact_email       = @contact_email,
        contact_phone       = @contact_phone,
        updated_at          = GETDATE(),
        updated_by          = @updated_by
    WHERE tenant_id = @tenant_id;

    SELECT *
    FROM dbo.tenants
    WHERE tenant_id = @tenant_id;
END;
GO

/* ============================================================
   sp_Tenant_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_Tenant_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Tenant_Get;
GO

CREATE PROCEDURE dbo.sp_Tenant_Get
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        tenant_id,
        tenant_code,
        tenant_abbreviation,
        tenant_name,
        db_name,
        platform_version,
        tenant_db_version,
        contact_name,
        contact_email,
        contact_phone,
        is_active,
        created_at,
        created_by,
        updated_at,
        updated_by
    FROM dbo.tenants
    WHERE tenant_id = @tenant_id;
END;
GO

/* ============================================================
   sp_Tenant_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_Tenant_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Tenant_List;
GO

CREATE PROCEDURE dbo.sp_Tenant_List
(
    @search VARCHAR(200) = NULL,
    @is_active BIT = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        tenant_id,
        tenant_code,
        tenant_abbreviation,
        tenant_name,
        db_name,
        platform_version,
        tenant_db_version,
        contact_name,
        contact_email,
        contact_phone,
        is_active,
        created_at,
        updated_at
    FROM dbo.tenants
    WHERE
        (
            @search IS NULL
            OR tenant_code LIKE '%' + @search + '%'
            OR tenant_abbreviation LIKE '%' + @search + '%'
            OR tenant_name LIKE '%' + @search + '%'
        )
        AND
        (
            @is_active IS NULL
            OR is_active = @is_active
        )
    ORDER BY tenant_name;
END;
GO

/* ============================================================
   sp_Tenant_Activate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Tenant_Activate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Tenant_Activate;
GO

CREATE PROCEDURE dbo.sp_Tenant_Activate
(
    @tenant_id UNIQUEIDENTIFIER,
    @updated_by UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.tenants
    SET
        is_active = 1,
        updated_at = GETDATE(),
        updated_by = @updated_by
    WHERE tenant_id = @tenant_id;

    SELECT *
    FROM dbo.tenants
    WHERE tenant_id = @tenant_id;
END;
GO

/* ============================================================
   sp_Tenant_Deactivate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Tenant_Deactivate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Tenant_Deactivate;
GO

CREATE PROCEDURE dbo.sp_Tenant_Deactivate
(
    @tenant_id UNIQUEIDENTIFIER,
    @updated_by UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.tenants
    SET
        is_active = 0,
        updated_at = GETDATE(),
        updated_by = @updated_by
    WHERE tenant_id = @tenant_id;

    SELECT *
    FROM dbo.tenants
    WHERE tenant_id = @tenant_id;
END;
GO