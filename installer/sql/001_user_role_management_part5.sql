SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   AUTHENTICATION SUPPORT TABLE
   ============================================================ */

IF OBJECT_ID('dbo.user_login_security', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_login_security
    (
        user_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        failed_login_count INT NOT NULL DEFAULT(0),
        is_locked BIT NOT NULL DEFAULT(0),
        locked_until DATETIME NULL,
        force_password_change BIT NOT NULL DEFAULT(1),
        last_failed_login DATETIME NULL,
        last_successful_login DATETIME NULL
    );
END;
GO

/* ============================================================
   sp_User_ValidateLogin
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_ValidateLogin', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_ValidateLogin;
GO

CREATE PROCEDURE dbo.sp_User_ValidateLogin
(
    @username VARCHAR(100),
    @password_hash VARCHAR(500)
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @user_id UNIQUEIDENTIFIER;
    DECLARE @db_password_hash VARCHAR(500);
    DECLARE @is_active BIT;
    DECLARE @is_locked BIT;
    DECLARE @locked_until DATETIME;

    SELECT
        @user_id = user_id,
        @db_password_hash = password_hash,
        @is_active = is_active
    FROM dbo.users
    WHERE username = @username;

    IF @user_id IS NULL
        THROW 57001, 'Invalid username or password.', 1;

    IF @is_active = 0
        THROW 57002, 'User account is inactive.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.user_login_security
        WHERE user_id = @user_id
    )
    BEGIN
        INSERT INTO dbo.user_login_security
        (
            user_id,
            failed_login_count,
            is_locked,
            force_password_change
        )
        VALUES
        (
            @user_id,
            0,
            0,
            1
        );
    END;

    SELECT
        @is_locked = is_locked,
        @locked_until = locked_until
    FROM dbo.user_login_security
    WHERE user_id = @user_id;

    IF @is_locked = 1
       AND @locked_until > GETDATE()
        THROW 57003, 'Account locked.', 1;

    IF @db_password_hash <> @password_hash
        THROW 57004, 'Invalid username or password.', 1;

    SELECT
        u.user_id,
        u.tenant_id,
        u.username,
        u.first_name,
        u.last_name,
        u.is_platform_user,
        s.force_password_change,
        s.failed_login_count,
        s.last_successful_login
    FROM dbo.users u
    INNER JOIN dbo.user_login_security s
        ON u.user_id = s.user_id
    WHERE u.user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_LoginSuccess
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_LoginSuccess', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_LoginSuccess;
GO

CREATE PROCEDURE dbo.sp_User_LoginSuccess
(
    @user_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.user_login_security
        WHERE user_id = @user_id
    )
    BEGIN
        INSERT INTO dbo.user_login_security
        (
            user_id
        )
        VALUES
        (
            @user_id
        );
    END;

    UPDATE dbo.user_login_security
    SET
        failed_login_count = 0,
        is_locked = 0,
        locked_until = NULL,
        last_successful_login = GETDATE()
    WHERE user_id = @user_id;

    UPDATE dbo.users
    SET
        last_login = GETDATE(),
        updated_at = GETDATE()
    WHERE user_id = @user_id;

    SELECT
        user_id,
        failed_login_count,
        is_locked,
        last_successful_login
    FROM dbo.user_login_security
    WHERE user_id = @user_id;
END;
GO

/* ============================================================
   sp_User_LoginFailure
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_LoginFailure', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_LoginFailure;
GO

CREATE PROCEDURE dbo.sp_User_LoginFailure
(
    @username VARCHAR(100)
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @user_id UNIQUEIDENTIFIER;

    SELECT
        @user_id = user_id
    FROM dbo.users
    WHERE username = @username;

    IF @user_id IS NULL
        RETURN;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.user_login_security
        WHERE user_id = @user_id
    )
    BEGIN
        INSERT INTO dbo.user_login_security
        (
            user_id
        )
        VALUES
        (
            @user_id
        );
    END;

    UPDATE dbo.user_login_security
    SET
        failed_login_count = failed_login_count + 1,
        last_failed_login = GETDATE()
    WHERE user_id = @user_id;

    UPDATE dbo.user_login_security
    SET
        is_locked = 1,
        locked_until = DATEADD(MINUTE, 30, GETDATE())
    WHERE user_id = @user_id
      AND failed_login_count >= 5;

    SELECT
        user_id,
        failed_login_count,
        is_locked,
        locked_until,
        last_failed_login
    FROM dbo.user_login_security
    WHERE user_id = @user_id;
END;
GO