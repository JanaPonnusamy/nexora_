SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Dashboard_GetExecutionHistory
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetExecutionHistory', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetExecutionHistory;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetExecutionHistory
(
    @tenant_id UNIQUEIDENTIFIER,
    @from_date DATETIME = NULL,
    @to_date DATETIME = NULL,
    @store_id UNIQUEIDENTIFIER = NULL,
    @status VARCHAR(50) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    IF @from_date IS NULL
        SET @from_date = DATEADD(DAY, -30, GETDATE());

    IF @to_date IS NULL
        SET @to_date = GETDATE();

    SELECT
        h.sync_id,

        h.tenant_id,

        h.store_id,
        s.store_code,
        s.store_name,

        h.sync_mode,
        h.sync_type,

        h.started_at,
        h.completed_at,

        h.duration_seconds,

        h.total_rows,
        h.processed_rows,
        h.failed_rows,

        h.status,

        h.triggered_by,

        u.username AS triggered_by_username,

        h.error_message,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_details d
            WHERE d.sync_id = h.sync_id
        ) AS total_chunks,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_details d
            WHERE d.sync_id = h.sync_id
              AND d.status IN ('SUCCESS','COMPLETED')
        ) AS completed_chunks,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_details d
            WHERE d.sync_id = h.sync_id
              AND d.status IN ('FAILED','ERROR')
        ) AS failed_chunks,

        (
            SELECT COUNT(*)
            FROM dbo.sync_execution_details d
            WHERE d.sync_id = h.sync_id
              AND d.status IN ('RUNNING','IN_PROGRESS')
        ) AS running_chunks

    FROM dbo.sync_execution_history h

    INNER JOIN dbo.stores s
        ON h.store_id = s.store_id

    LEFT JOIN dbo.users u
        ON h.triggered_by = u.user_id

    WHERE
        h.tenant_id = @tenant_id

        AND h.started_at >= @from_date

        AND h.started_at < DATEADD(DAY, 1, @to_date)

        AND
        (
            @store_id IS NULL
            OR h.store_id = @store_id
        )

        AND
        (
            @status IS NULL
            OR h.status = @status
        )

    ORDER BY
        h.started_at DESC,
        h.sync_id DESC;
END;
GO