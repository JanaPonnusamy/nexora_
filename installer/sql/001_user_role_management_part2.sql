SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Role_Create
   ============================================================ */

IF OBJECT_ID('dbo.sp_Role_Create', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Role_Create;
GO

CREATE PROCEDURE dbo.sp_Role_Create
(
    @role_name VARCHAR(50),
    @description VARCHAR(500) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@role_name)), '') IS NULL
        THROW 54001, 'Role name is required.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_name = @role_name
    )
        THROW 54002, 'Role already exists.', 1;

    DECLARE @role_id UNIQUEIDENTIFIER = NEWID();

    INSERT INTO dbo.roles
    (
        role_id,
        role_name,
        description,
        is_active
    )
    VALUES
    (
        @role_id,
        @role_name,
        @description,
        1
    );

    SELECT *
    FROM dbo.roles
    WHERE role_id = @role_id;
END;
GO

/* ============================================================
   sp_Role_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_Role_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Role_Update;
GO

CREATE PROCEDURE dbo.sp_Role_Update
(
    @role_id UNIQUEIDENTIFIER,
    @role_name VARCHAR(50),
    @description VARCHAR(500) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_id = @role_id
    )
        THROW 54003, 'Role not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_name = @role_name
          AND role_id <> @role_id
    )
        THROW 54004, 'Role name already exists.', 1;

    UPDATE dbo.roles
    SET
        role_name = @role_name,
        description = @description
    WHERE role_id = @role_id;

    SELECT *
    FROM dbo.roles
    WHERE role_id = @role_id;
END;
GO

/* ============================================================
   sp_Role_Get
   ============================================================ */

IF OBJECT_ID('dbo.sp_Role_Get', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Role_Get;
GO

CREATE PROCEDURE dbo.sp_Role_Get
(
    @role_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        role_id,
        role_name,
        description,
        is_active
    FROM dbo.roles
    WHERE role_id = @role_id;
END;
GO

/* ============================================================
   sp_Role_List
   ============================================================ */

IF OBJECT_ID('dbo.sp_Role_List', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Role_List;
GO

CREATE PROCEDURE dbo.sp_Role_List
(
    @is_active BIT = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        role_id,
        role_name,
        description,
        is_active
    FROM dbo.roles
    WHERE
        (
            @is_active IS NULL
            OR is_active = @is_active
        )
    ORDER BY role_name;
END;
GO

/* ============================================================
   sp_Role_Activate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Role_Activate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Role_Activate;
GO

CREATE PROCEDURE dbo.sp_Role_Activate
(
    @role_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_id = @role_id
    )
        THROW 54005, 'Role not found.', 1;

    UPDATE dbo.roles
    SET
        is_active = 1
    WHERE role_id = @role_id;

    SELECT *
    FROM dbo.roles
    WHERE role_id = @role_id;
END;
GO

/* ============================================================
   sp_Role_Deactivate
   ============================================================ */

IF OBJECT_ID('dbo.sp_Role_Deactivate', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Role_Deactivate;
GO

CREATE PROCEDURE dbo.sp_Role_Deactivate
(
    @role_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.roles
        WHERE role_id = @role_id
    )
        THROW 54006, 'Role not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.user_store_roles
        WHERE role_id = @role_id
          AND is_active = 1
    )
        THROW 54007, 'Role is assigned to active users and cannot be deactivated.', 1;

    UPDATE dbo.roles
    SET
        is_active = 0
    WHERE role_id = @role_id;

    SELECT *
    FROM dbo.roles
    WHERE role_id = @role_id;
END;
GO