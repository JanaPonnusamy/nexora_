SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_User_Create
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_Create', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_Create;
GO

CREATE PROCEDURE dbo.sp_User_Create
(
    @tenant_id UNIQUEIDENTIFIER = NULL,
    @username VARCHAR(100),
    @password_hash VARCHAR(500),
    @first_name VARCHAR(100),
    @last_name VARCHAR(100) = NULL,
    @email VARCHAR(200) = NULL,
    @mobile VARCHAR(50) = NULL,
    @is_platform_user BIT = 0
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@username)), '') IS NULL
        THROW 53001, 'Username is required.', 1;

    IF NULLIF(LTRIM(RTRIM(@first_name)), '') IS NULL
        THROW 53002, 'First name is required.', 1;

    IF LEN(@password_hash) < 5
        THROW 53003, 'Password policy violation.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.users
        WHERE username = @username
    )
        THROW 53004, 'Username already exists.', 1;

    IF @is_platform_user = 0
       AND @tenant_id IS NULL
        THROW 53005, 'Tenant is required.', 1;

    DECLARE @user_id UNIQUEIDENTIFIER = NEWID();

    INSERT INTO dbo.users
    (
        user_id,
        tenant_id,
        username,
        password_hash,
        first_name,
        last_name,
        email,
        mobile,
        is_platform_user,
        is_active,
        created_at
    )
    VALUES
    (
        @user_id,
        @tenant_id,
        @username,
        @password_hash,
        @first_name,
        @last_name,
        @email,
        @mobile,
        @is_platform_user,
        1,
        GETDATE()
    );

    SELECT *
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_Update;
GO

CREATE PROCEDURE dbo.sp_User_Update
(
    @user_id UNIQUEIDENTIFIER,
    @first_name VARCHAR(100),
    @last_name VARCHAR(100) = NULL,
    @email VARCHAR(200) = NULL,
    @mobile VARCHAR(50) = NULL,
    @tenant_id UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.users
        WHERE user_id = @user_id
    )
        THROW 53006, 'User not found.', 1;

    UPDATE dbo.users
    SET
        first_name = @first_name,
        last_name = @last_name,
        email = @email,
        mobile = @mobile,
        tenant_id = @tenant_id,
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT *
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_Get;
GO

CREATE PROCEDURE dbo.sp_User_Get
(
    @user_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        u.*,
        t.tenant_code,
        t.tenant_name
    FROM dbo.users u
    LEFT JOIN dbo.tenants t
        ON u.tenant_id = t.tenant_id
    WHERE u.user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_List;
GO

CREATE PROCEDURE dbo.sp_User_List
(
    @tenant_id UNIQUEIDENTIFIER = NULL,
    @is_active BIT = NULL,
    @search VARCHAR(200) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        u.user_id,
        u.username,
        u.first_name,
        u.last_name,
        u.email,
        u.mobile,
        u.is_platform_user,
        u.is_active,
        u.last_login,
        u.created_at,
        t.tenant_name
    FROM dbo.users u
    LEFT JOIN dbo.tenants t
        ON u.tenant_id = t.tenant_id
    WHERE
        (
            @tenant_id IS NULL
            OR u.tenant_id = @tenant_id
        )
        AND
        (
            @is_active IS NULL
            OR u.is_active = @is_active
        )
        AND
        (
            @search IS NULL
            OR u.username LIKE '%' + @search + '%'
            OR u.first_name LIKE '%' + @search + '%'
            OR u.last_name LIKE '%' + @search + '%'
            OR u.email LIKE '%' + @search + '%'
        )
    ORDER BY
        u.first_name,
        u.last_name;
END;
GO

/* ============================================================
   sp_User_Activate
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_Activate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_Activate;
GO

CREATE PROCEDURE dbo.sp_User_Activate
(
    @user_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.users
    SET
        is_active = 1,
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT *
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_Deactivate
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_Deactivate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_Deactivate;
GO

CREATE PROCEDURE dbo.sp_User_Deactivate
(
    @user_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.users
    SET
        is_active = 0,
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT *
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_ResetPassword
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_ResetPassword', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_ResetPassword;
GO

CREATE PROCEDURE dbo.sp_User_ResetPassword
(
    @user_id UNIQUEIDENTIFIER,
    @password_hash VARCHAR(500)
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.users
    SET
        password_hash = @password_hash,
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT
        user_id,
        username,
        updated_at
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_Unlock
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_Unlock', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_Unlock;
GO

CREATE PROCEDURE dbo.sp_User_Unlock
(
    @user_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.users
    SET
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT
        user_id,
        username,
        is_active,
        updated_at
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_ChangePassword
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_ChangePassword', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_ChangePassword;
GO

CREATE PROCEDURE dbo.sp_User_ChangePassword
(
    @user_id UNIQUEIDENTIFIER,
    @old_password_hash VARCHAR(500),
    @new_password_hash VARCHAR(500)
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.users
        WHERE user_id = @user_id
          AND password_hash = @old_password_hash
    )
        THROW 53007, 'Invalid current password.', 1;

    UPDATE dbo.users
    SET
        password_hash = @new_password_hash,
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT
        user_id,
        username,
        updated_at
    FROM dbo.users
    WHERE user_id = @user_id;
END;
GO