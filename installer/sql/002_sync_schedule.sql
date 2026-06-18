SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncSchedule_Create
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncSchedule_Create', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncSchedule_Create;
GO

CREATE PROCEDURE dbo.sp_SyncSchedule_Create
(
    @tenant_id UNIQUEIDENTIFIER,
    @schedule_name VARCHAR(100),
    @schedule_type VARCHAR(50),
    @start_time DATETIME
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
        THROW 60101, 'Tenant not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_schedule
        WHERE tenant_id = @tenant_id
          AND schedule_name = @schedule_name
    )
        THROW 60102, 'Schedule already exists.', 1;

    INSERT INTO dbo.sync_schedule
    (
        tenant_id,
        schedule_name,
        schedule_type,
        start_time,
        is_enabled,
        created_at
    )
    VALUES
    (
        @tenant_id,
        @schedule_name,
        @schedule_type,
        @start_time,
        1,
        GETDATE()
    );

    SELECT *
    FROM dbo.sync_schedule
    WHERE schedule_id = SCOPE_IDENTITY();
END;
GO

/* ============================================================
   sp_SyncSchedule_Update
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncSchedule_Update', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncSchedule_Update;
GO

CREATE PROCEDURE dbo.sp_SyncSchedule_Update
(
    @schedule_id BIGINT,
    @schedule_name VARCHAR(100),
    @schedule_type VARCHAR(50),
    @start_time DATETIME
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.sync_schedule
        WHERE schedule_id = @schedule_id
    )
        THROW 60103, 'Schedule not found.', 1;

    UPDATE dbo.sync_schedule
    SET
        schedule_name = @schedule_name,
        schedule_type = @schedule_type,
        start_time = @start_time
    WHERE schedule_id = @schedule_id;

    SELECT *
    FROM dbo.sync_schedule
    WHERE schedule_id = @schedule_id;
END;
GO

/* ============================================================
   sp_SyncSchedule_Enable
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncSchedule_Enable', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncSchedule_Enable;
GO

CREATE PROCEDURE dbo.sp_SyncSchedule_Enable
(
    @schedule_id BIGINT
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sync_schedule
    SET
        is_enabled = 1
    WHERE schedule_id = @schedule_id;

    SELECT *
    FROM dbo.sync_schedule
    WHERE schedule_id = @schedule_id;
END;
GO

/* ============================================================
   sp_SyncSchedule_Disable
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncSchedule_Disable', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncSchedule_Disable;
GO

CREATE PROCEDURE dbo.sp_SyncSchedule_Disable
(
    @schedule_id BIGINT
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sync_schedule
    SET
        is_enabled = 0
    WHERE schedule_id = @schedule_id;

    SELECT *
    FROM dbo.sync_schedule
    WHERE schedule_id = @schedule_id;
END;
GO