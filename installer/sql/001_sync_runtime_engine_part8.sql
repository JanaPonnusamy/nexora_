IF OBJECT_ID('dbo.sp_Runtime_GetExecutionStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_GetExecutionStatus
GO

CREATE PROCEDURE dbo.sp_Runtime_GetExecutionStatus
(
    @execution_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        execution_id,
        tenant_id,
        store_id,
        execution_type,
        sync_mode,
        execution_status,
        started_at,
        completed_at,
        total_tables,
        completed_tables,
        failed_tables,
        initiated_by,
        created_by
    FROM dbo.sync_execution
    WHERE execution_id = @execution_id;
END
GO

IF OBJECT_ID('dbo.sp_Runtime_GetChunkStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_GetChunkStatus
GO

CREATE PROCEDURE dbo.sp_Runtime_GetChunkStatus
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
    ORDER BY table_name,
             chunk_no;
END
GO
