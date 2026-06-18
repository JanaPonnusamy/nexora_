IF OBJECT_ID('dbo.sp_Runtime_GetRetryItems', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_GetRetryItems
GO

CREATE PROCEDURE dbo.sp_Runtime_GetRetryItems
(
    @execution_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        chunk_execution_id,
        execution_id,
        table_name,
        chunk_no,
        chunk_status,
        rows_processed,
        retry_count,
        started_at,
        completed_at,
        error_message
    FROM dbo.sync_chunk_execution
    WHERE execution_id = @execution_id
      AND chunk_status = 'FAILED'
    ORDER BY retry_count,
             chunk_execution_id;
END
GO

IF OBJECT_ID('dbo.sp_Runtime_SaveRetryResult', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_SaveRetryResult
GO

CREATE PROCEDURE dbo.sp_Runtime_SaveRetryResult
(
    @chunk_execution_id BIGINT,
    @retry_success BIT,
    @rows_processed BIGINT = 0,
    @error_message NVARCHAR(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sync_chunk_execution
    SET retry_count = ISNULL(retry_count,0) + 1,
        chunk_status = CASE
                          WHEN @retry_success = 1 THEN 'COMPLETED'
                          ELSE 'FAILED'
                       END,
        rows_processed = @rows_processed,
        error_message = @error_message,
        completed_at = GETDATE()
    WHERE chunk_execution_id = @chunk_execution_id;

    SELECT *
    FROM dbo.sync_chunk_execution
    WHERE chunk_execution_id = @chunk_execution_id;
END
GO
