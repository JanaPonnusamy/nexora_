SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncRefreshCycle_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncRefreshCycle_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncRefreshCycle_Save;
GO

CREATE PROCEDURE dbo.sp_SyncRefreshCycle_Save
(
    @tenant_id UNIQUEIDENTIFIER,
    @cycle_name VARCHAR(100),
    @refresh_type VARCHAR(50),
    @refresh_interval_minutes INT,
    @is_active BIT = 1
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
        THROW 60601, 'Tenant not found.', 1;

    IF NULLIF(LTRIM(RTRIM(@cycle_name)), '') IS NULL
        THROW 60602, 'Cycle name is required.', 1;

    IF @refresh_interval_minutes <= 0
        THROW 60603, 'Refresh interval must be greater than zero.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_refresh_cycles
        WHERE tenant_id = @tenant_id
          AND cycle_name = @cycle_name
    )
    BEGIN
        UPDATE dbo.sync_refresh_cycles
        SET
            refresh_type = @refresh_type,
            refresh_interval_minutes = @refresh_interval_minutes,
            is_active = @is_active
        WHERE tenant_id = @tenant_id
          AND cycle_name = @cycle_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.sync_refresh_cycles
        (
            tenant_id,
            cycle_name,
            refresh_type,
            refresh_interval_minutes,
            is_active
        )
        VALUES
        (
            @tenant_id,
            @cycle_name,
            @refresh_type,
            @refresh_interval_minutes,
            @is_active
        );
    END;

    SELECT
        cycle_id,
        tenant_id,
        cycle_name,
        refresh_type,
        refresh_interval_minutes,
        is_active
    FROM dbo.sync_refresh_cycles
    WHERE tenant_id = @tenant_id
      AND cycle_name = @cycle_name;
END;
GO