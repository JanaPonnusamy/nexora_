SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Dashboard_GetRunningSyncs
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetRunningSyncs', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetRunningSyncs;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetRunningSyncs
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        h.sync_id,

        s.store_id,
        s.store_code,
        s.store_name,

        d.table_name,

        d.chunk_no,

        d.status,

        d.started_at,

        ISNULL
        (
            d.duration_seconds,
            DATEDIFF(SECOND, d.started_at, GETDATE())
        ) AS duration_seconds,

        CASE
            WHEN d.chunk_size = 0
                THEN 0

            ELSE
                CAST
                (
                    (
                        CAST(d.rows_processed AS DECIMAL(18,2))
                        /
                        CAST(d.chunk_size AS DECIMAL(18,2))
                    ) * 100
                    AS DECIMAL(10,2)
                )
        END AS progress_percentage,

        d.rows_processed,
        d.rows_failed,

        h.sync_mode,
        h.sync_type

    FROM dbo.sync_execution_history h

    INNER JOIN dbo.sync_execution_details d
        ON h.sync_id = d.sync_id

    INNER JOIN dbo.stores s
        ON h.store_id = s.store_id

    WHERE
        h.tenant_id = @tenant_id
        AND
        (
            h.status IN
            (
                'RUNNING',
                'IN_PROGRESS'
            )
            OR
            d.status IN
            (
                'RUNNING',
                'IN_PROGRESS'
            )
        )

    ORDER BY
        d.started_at DESC;
END;
GO

/* ============================================================
   sp_Dashboard_GetFailedSyncs
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetFailedSyncs', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetFailedSyncs;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetFailedSyncs
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        h.sync_id,

        s.store_id,
        s.store_code,
        s.store_name,

        d.table_name,

        ISNULL
        (
            d.error_message,
            h.error_message
        ) AS error_message,

        rr.max_retry_count,

        rr.retry_interval_minutes,

        h.failed_rows,

        h.completed_at AS last_attempt,

        h.status,

        d.chunk_no,

        d.rows_failed,

        d.duration_seconds

    FROM dbo.sync_execution_history h

    INNER JOIN dbo.sync_execution_details d
        ON h.sync_id = d.sync_id

    INNER JOIN dbo.stores s
        ON h.store_id = s.store_id

    LEFT JOIN dbo.sync_retry_rules rr
        ON rr.tenant_id = h.tenant_id
       AND rr.is_active = 1

    WHERE
        h.tenant_id = @tenant_id
        AND
        (
            h.status IN
            (
                'FAILED',
                'ERROR'
            )
            OR
            d.status IN
            (
                'FAILED',
                'ERROR'
            )
        )

    ORDER BY
        h.completed_at DESC,
        h.sync_id DESC;
END;
GO