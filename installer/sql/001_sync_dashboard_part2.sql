SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Dashboard_GetSummary
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetSummary', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetSummary;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetSummary
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        t.tenant_id,
        t.tenant_name,

        (
            SELECT COUNT(*)
            FROM dbo.stores s
            WHERE s.tenant_id = @tenant_id
              AND s.is_active = 1
        ) AS total_stores,

        (
            SELECT COUNT(*)
            FROM dbo.stores s
            WHERE s.tenant_id = @tenant_id
              AND s.connection_status IN ('ONLINE','ACTIVE','CONNECTED')
        ) AS online_stores,

        (
            SELECT COUNT(*)
            FROM dbo.stores s
            WHERE s.tenant_id = @tenant_id
              AND
              (
                  s.connection_status IS NULL
                  OR s.connection_status IN
                  (
                      'OFFLINE',
                      'DISCONNECTED',
                      'FAILED'
                  )
              )
        ) AS offline_stores,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_history h
            WHERE h.tenant_id = @tenant_id
              AND h.status IN
              (
                  'RUNNING',
                  'IN_PROGRESS'
              )
        ) AS running_syncs,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_history h
            WHERE h.tenant_id = @tenant_id
              AND h.status IN
              (
                  'FAILED',
                  'ERROR'
              )
        ) AS failed_syncs,

        (
            SELECT COUNT(*)
            FROM dbo.sync_manual_trigger mt
            WHERE mt.tenant_id = @tenant_id
              AND mt.approval_status = 'PENDING'
        ) AS pending_approvals,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_history h
            WHERE h.tenant_id = @tenant_id
              AND CAST(h.started_at AS DATE) = CAST(GETDATE() AS DATE)
        ) AS today_sync_count,

        (
            SELECT ISNULL(SUM(h.processed_rows),0)
            FROM dbo.sync_execution_history h
            WHERE h.tenant_id = @tenant_id
              AND CAST(h.started_at AS DATE) = CAST(GETDATE() AS DATE)
        ) AS data_processed_today,

        (
            SELECT MAX(h.completed_at)
            FROM dbo.sync_execution_history h
            WHERE h.tenant_id = @tenant_id
        ) AS last_refresh

    FROM dbo.tenants t
    WHERE t.tenant_id = @tenant_id;
END;
GO

/* ============================================================
   sp_Dashboard_GetStoreStatus
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetStoreStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetStoreStatus;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetStoreStatus
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        s.store_id,

        s.store_code,

        s.store_name,

        s.connection_status,

        s.agent_version,

        s.last_heartbeat,

        s.last_seen,

        h.last_sync_time,

        h.last_sync_status,

        CASE
            WHEN s.last_heartbeat IS NULL
                THEN 'UNKNOWN'

            WHEN DATEDIFF(MINUTE, s.last_heartbeat, GETDATE()) <= 5
                THEN 'ONLINE'

            WHEN DATEDIFF(MINUTE, s.last_heartbeat, GETDATE()) <= 30
                THEN 'WARNING'

            ELSE 'OFFLINE'
        END AS heartbeat_status,

        CASE
            WHEN h.last_sync_status IS NULL
                THEN 'NOT_STARTED'

            ELSE h.last_sync_status
        END AS sync_status,

        DATEDIFF
        (
            MINUTE,
            s.last_heartbeat,
            GETDATE()
        ) AS minutes_since_heartbeat

    FROM dbo.stores s

    OUTER APPLY
    (
        SELECT TOP 1
            eh.completed_at AS last_sync_time,
            eh.status AS last_sync_status
        FROM dbo.sync_execution_history eh
        WHERE eh.store_id = s.store_id
        ORDER BY eh.sync_id DESC
    ) h

    WHERE s.tenant_id = @tenant_id

    ORDER BY
        s.store_name;
END;
GO