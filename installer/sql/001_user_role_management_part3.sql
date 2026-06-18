SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_User_AssignStoreRole
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_AssignStoreRole', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_AssignStoreRole;
GO

CREATE PROCEDURE dbo.sp_User_AssignStoreRole
(
    @user_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,
    @role_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.users
        WHERE user_id = @user_id
          AND is_active = 1
    )
        THROW 55001, 'User not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND is_active = 1
    )
        THROW 55002, 'Store not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_id = @role_id
          AND is_active = 1
    )
        THROW 55003, 'Role not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.user_store_roles
        WHERE user_id = @user_id
          AND store_id = @store_id
          AND is_active = 1
    )
    BEGIN
        UPDATE dbo.user_store_roles
        SET
            role_id = @role_id
        WHERE user_id = @user_id
          AND store_id = @store_id
          AND is_active = 1;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.user_store_roles
        (
            user_id,
            store_id,
            role_id,
            is_active
        )
        VALUES
        (
            @user_id,
            @store_id,
            @role_id,
            1
        );
    END

    SELECT
        usr.id,
        usr.user_id,
        u.username,
        usr.store_id,
        s.store_code,
        s.store_name,
        usr.role_id,
        r.role_name,
        usr.is_active
    FROM dbo.user_store_roles usr
    INNER JOIN dbo.users u
        ON usr.user_id = u.user_id
    INNER JOIN dbo.stores s
        ON usr.store_id = s.store_id
    INNER JOIN dbo.roles r
        ON usr.role_id = r.role_id
    WHERE usr.user_id = @user_id
      AND usr.store_id = @store_id
      AND usr.is_active = 1;
END;
GO

/* ============================================================
   sp_User_RemoveStoreRole
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_RemoveStoreRole', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_RemoveStoreRole;
GO

CREATE PROCEDURE dbo.sp_User_RemoveStoreRole
(
    @user_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.user_store_roles
    SET
        is_active = 0
    WHERE user_id = @user_id
      AND store_id = @store_id
      AND is_active = 1;

    SELECT
        @user_id AS user_id,
        @store_id AS store_id,
        CAST(1 AS BIT) AS role_removed;
END;
GO

/* ============================================================
   sp_User_StoreRole_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_User_StoreRole_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_User_StoreRole_List;
GO

CREATE PROCEDURE dbo.sp_User_StoreRole_List
(
    @user_id UNIQUEIDENTIFIER = NULL,
    @store_id UNIQUEIDENTIFIER = NULL,
    @tenant_id UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        usr.id,
        usr.user_id,
        u.username,
        u.first_name,
        u.last_name,

        usr.store_id,
        s.store_code,
        s.store_name,

        s.tenant_id,
        t.tenant_code,
        t.tenant_name,

        usr.role_id,
        r.role_name,

        usr.is_active
    FROM dbo.user_store_roles usr
    INNER JOIN dbo.users u
        ON usr.user_id = u.user_id
    INNER JOIN dbo.stores s
        ON usr.store_id = s.store_id
    INNER JOIN dbo.tenants t
        ON s.tenant_id = t.tenant_id
    INNER JOIN dbo.roles r
        ON usr.role_id = r.role_id
    WHERE
        (
            @user_id IS NULL
            OR usr.user_id = @user_id
        )
        AND
        (
            @store_id IS NULL
            OR usr.store_id = @store_id
        )
        AND
        (
            @tenant_id IS NULL
            OR s.tenant_id = @tenant_id
        )
        AND usr.is_active = 1
    ORDER BY
        t.tenant_name,
        s.store_name,
        u.username;
END;
GO