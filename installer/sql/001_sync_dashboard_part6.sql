SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Dashboard_GetDashboardSnapshot
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetDashboardSnapshot', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetDashboardSnapshot;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetDashboardSnapshot
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP 1
        snapshot_id,

        tenant_id,

        total_stores,

        online_stores,

        offline_stores,

        running_syncs,

        failed_syncs,

        pending_approvals,

        today_sync_count,

        data_processed_today,

        snapshot_time

    FROM dbo.sync_dashboard_snapshot

    WHERE tenant_id = @tenant_id

    ORDER BY
        snapshot_time DESC,
        snapshot_id DESC;
END;
GO

/* ============================================================
   sp_Dashboard_RefreshSnapshot
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_RefreshSnapshot', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_RefreshSnapshot;
GO

CREATE PROCEDURE dbo.sp_Dashboard_RefreshSnapshot
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @total_stores INT = 0;
    DECLARE @online_stores INT = 0;
    DECLARE @offline_stores INT = 0;
    DECLARE @running_syncs INT = 0;
    DECLARE @failed_syncs INT = 0;
    DECLARE @pending_approvals INT = 0;
    DECLARE @today_sync_count INT = 0;
    DECLARE @data_processed_today BIGINT = 0;

    SELECT
        @total_stores = COUNT(*)
    FROM dbo.stores
    WHERE tenant_id = @tenant_id
      AND is_active = 1;

    SELECT
        @online_stores = COUNT(*)
    FROM dbo.stores
    WHERE tenant_id = @tenant_id
      AND connection_status IN
      (
          'ONLINE',
          'ACTIVE',
          'CONNECTED'
      );

    SELECT
        @offline_stores = COUNT(*)
    FROM dbo.stores
    WHERE tenant_id = @tenant_id
      AND
      (
          connection_status IS NULL
          OR connection_status IN
          (
              'OFFLINE',
              'DISCONNECTED',
              'FAILED'
          )
      );

    SELECT
        @running_syncs = COUNT(*)
    FROM dbo.sync_execution_history
    WHERE tenant_id = @tenant_id
      AND status IN
      (
          'RUNNING',
          'IN_PROGRESS'
      );

    SELECT
        @failed_syncs = COUNT(*)
    FROM dbo.sync_execution_history
    WHERE tenant_id = @tenant_id
      AND status IN
      (
          'FAILED',
          'ERROR'
      );

    SELECT
        @pending_approvals = COUNT(*)
    FROM dbo.sync_manual_trigger
    WHERE tenant_id = @tenant_id
      AND approval_status = 'PENDING';

    SELECT
        @today_sync_count = COUNT(*)
    FROM dbo.sync_execution_history
    WHERE tenant_id = @tenant_id
      AND CAST(started_at AS DATE) = CAST(GETDATE() AS DATE);

    SELECT
        @data_processed_today =
            ISNULL(SUM(processed_rows),0)
    FROM dbo.sync_execution_history
    WHERE tenant_id = @tenant_id
      AND CAST(started_at AS DATE) = CAST(GETDATE() AS DATE);

    INSERT INTO dbo.sync_dashboard_snapshot
    (
        tenant_id,

        total_stores,

        online_stores,

        offline_stores,

        running_syncs,

        failed_syncs,

        pending_approvals,

        today_sync_count,

        data_processed_today,

        snapshot_time
    )
    VALUES
    (
        @tenant_id,

        @total_stores,

        @online_stores,

        @offline_stores,

        @running_syncs,

        @failed_syncs,

        @pending_approvals,

        @today_sync_count,

        @data_processed_today,

        GETDATE()
    );

    SELECT
        snapshot_id,

        tenant_id,

        total_stores,

        online_stores,

        offline_stores,

        running_syncs,

        failed_syncs,

        pending_approvals,

        today_sync_count,

        data_processed_today,

        snapshot_time

    FROM dbo.sync_dashboard_snapshot

    WHERE snapshot_id = SCOPE_IDENTITY();
END;
GO