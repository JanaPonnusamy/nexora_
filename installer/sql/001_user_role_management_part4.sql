SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_RoleModuleAccess_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_RoleModuleAccess_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_RoleModuleAccess_Save;
GO

CREATE PROCEDURE dbo.sp_RoleModuleAccess_Save
(
    @role_id UNIQUEIDENTIFIER,
    @module_id UNIQUEIDENTIFIER,
    @can_view BIT = 0,
    @can_create BIT = 0,
    @can_edit BIT = 0,
    @can_delete BIT = 0,
    @can_export BIT = 0,
    @is_active BIT = 1
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_id = @role_id
          AND is_active = 1
    )
        THROW 56001, 'Role not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.modules
        WHERE module_id = @module_id
          AND is_active = 1
    )
        THROW 56002, 'Module not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.role_module_access
        WHERE role_id = @role_id
          AND module_id = @module_id
    )
    BEGIN
        UPDATE dbo.role_module_access
        SET
            can_view = @can_view,
            can_create = @can_create,
            can_edit = @can_edit,
            can_delete = @can_delete,
            can_export = @can_export,
            is_active = @is_active
        WHERE role_id = @role_id
          AND module_id = @module_id;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.role_module_access
        (
            role_id,
            module_id,
            can_view,
            can_create,
            can_edit,
            can_delete,
            can_export,
            is_active
        )
        VALUES
        (
            @role_id,
            @module_id,
            @can_view,
            @can_create,
            @can_edit,
            @can_delete,
            @can_export,
            @is_active
        );
    END

    SELECT
        rma.id,
        rma.role_id,
        r.role_name,
        rma.module_id,
        m.module_code,
        m.module_name,
        rma.can_view,
        rma.can_create,
        rma.can_edit,
        rma.can_delete,
        rma.can_export,
        rma.is_active
    FROM dbo.role_module_access rma
    INNER JOIN dbo.roles r
        ON rma.role_id = r.role_id
    INNER JOIN dbo.modules m
        ON rma.module_id = m.module_id
    WHERE rma.role_id = @role_id
      AND rma.module_id = @module_id;
END;
GO

/* ============================================================
   sp_RoleModuleAccess_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_RoleModuleAccess_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_RoleModuleAccess_Get;
GO

CREATE PROCEDURE dbo.sp_RoleModuleAccess_Get
(
    @role_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        rma.id,
        rma.role_id,
        r.role_name,
        rma.module_id,
        m.module_code,
        m.module_name,
        rma.can_view,
        rma.can_create,
        rma.can_edit,
        rma.can_delete,
        rma.can_export,
        rma.is_active
    FROM dbo.role_module_access rma
    INNER JOIN dbo.roles r
        ON rma.role_id = r.role_id
    INNER JOIN dbo.modules m
        ON rma.module_id = m.module_id
    WHERE rma.role_id = @role_id
    ORDER BY m.module_name;
END;
GO

/* ============================================================
   sp_UserModuleOverride_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_UserModuleOverride_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_UserModuleOverride_Save;
GO

CREATE PROCEDURE dbo.sp_UserModuleOverride_Save
(
    @user_id UNIQUEIDENTIFIER,
    @module_id UNIQUEIDENTIFIER,
    @can_view BIT = 0,
    @can_create BIT = 0,
    @can_edit BIT = 0,
    @can_delete BIT = 0,
    @can_export BIT = 0,
    @is_active BIT = 1
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
        THROW 56003, 'User not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.modules
        WHERE module_id = @module_id
          AND is_active = 1
    )
        THROW 56004, 'Module not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.user_module_override
        WHERE user_id = @user_id
          AND module_id = @module_id
    )
    BEGIN
        UPDATE dbo.user_module_override
        SET
            can_view = @can_view,
            can_create = @can_create,
            can_edit = @can_edit,
            can_delete = @can_delete,
            can_export = @can_export,
            is_active = @is_active
        WHERE user_id = @user_id
          AND module_id = @module_id;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.user_module_override
        (
            user_id,
            module_id,
            can_view,
            can_create,
            can_edit,
            can_delete,
            can_export,
            is_active
        )
        VALUES
        (
            @user_id,
            @module_id,
            @can_view,
            @can_create,
            @can_edit,
            @can_delete,
            @can_export,
            @is_active
        );
    END

    SELECT
        umo.id,
        umo.user_id,
        u.username,
        umo.module_id,
        m.module_code,
        m.module_name,
        umo.can_view,
        umo.can_create,
        umo.can_edit,
        umo.can_delete,
        umo.can_export,
        umo.is_active
    FROM dbo.user_module_override umo
    INNER JOIN dbo.users u
        ON umo.user_id = u.user_id
    INNER JOIN dbo.modules m
        ON umo.module_id = m.module_id
    WHERE umo.user_id = @user_id
      AND umo.module_id = @module_id;
END;
GO

/* ============================================================
   sp_UserModuleOverride_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_UserModuleOverride_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_UserModuleOverride_Get;
GO

CREATE PROCEDURE dbo.sp_UserModuleOverride_Get
(
    @user_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        umo.id,
        umo.user_id,
        u.username,
        umo.module_id,
        m.module_code,
        m.module_name,
        umo.can_view,
        umo.can_create,
        umo.can_edit,
        umo.can_delete,
        umo.can_export,
        umo.is_active
    FROM dbo.user_module_override umo
    INNER JOIN dbo.users u
        ON umo.user_id = u.user_id
    INNER JOIN dbo.modules m
        ON umo.module_id = m.module_id
    WHERE umo.user_id = @user_id
    ORDER BY m.module_name;
END;
GO