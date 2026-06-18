IF OBJECT_ID('dbo.sp_Runtime_CreateChunks', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_CreateChunks
GO

CREATE PROCEDURE dbo.sp_Runtime_CreateChunks
(
    @execution_id UNIQUEIDENTIFIER,
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.sync_chunk_execution
    (
        execution_id,
        table_name,
        chunk_no,
        chunk_status,
        rows_processed,
        retry_count,
        started_at
    )
    SELECT
        @execution_id,
        r.table_name,
        1,
        'PENDING',
        0,
        0,
        NULL
    FROM dbo.sync_table_registry r
    WHERE r.tenant_id = @tenant_id
      AND r.is_active = 1
      AND r.chunk_enabled = 1;

    INSERT INTO dbo.sync_chunk_execution
    (
        execution_id,
        table_name,
        chunk_no,
        chunk_status,
        rows_processed,
        retry_count,
        started_at
    )
    SELECT
        @execution_id,
        r.table_name,
        1,
        'PENDING',
        0,
        0,
        NULL
    FROM dbo.sync_table_registry r
    WHERE r.tenant_id = @tenant_id
      AND r.is_active = 1
      AND ISNULL(r.chunk_enabled,0) = 0;

    SELECT *
    FROM dbo.sync_chunk_execution
    WHERE execution_id = @execution_id
    ORDER BY chunk_execution_id;
END
GO

IF OBJECT_ID('dbo.sp_Runtime_GetNextChunk', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_GetNextChunk
GO

CREATE PROCEDURE dbo.sp_Runtime_GetNextChunk
(
    @execution_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP 1
           chunk_execution_id,
           execution_id,
           table_name,
           chunk_no,
           chunk_status,
           rows_processed,
           retry_count,
           started_at,
           completed_at
    FROM dbo.sync_chunk_execution
    WHERE execution_id = @execution_id
      AND chunk_status = 'PENDING'
    ORDER BY chunk_execution_id;
END
GO

IF OBJECT_ID('dbo.sp_Runtime_UpdateChunkStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_UpdateChunkStatus
GO

CREATE PROCEDURE dbo.sp_Runtime_UpdateChunkStatus
(
    @chunk_execution_id BIGINT,
    @chunk_status VARCHAR(50),
    @rows_processed BIGINT = 0,
    @error_message NVARCHAR(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sync_chunk_execution
    SET chunk_status   = @chunk_status,
        rows_processed = @rows_processed,
        error_message  = @error_message,
        completed_at   = CASE
                            WHEN @chunk_status IN ('COMPLETED','FAILED')
                            THEN GETDATE()
                            ELSE completed_at
                         END,
        started_at     = CASE
                            WHEN started_at IS NULL
                                 AND @chunk_status = 'IN_PROGRESS'
                            THEN GETDATE()
                            ELSE started_at
                         END
    WHERE chunk_execution_id = @chunk_execution_id;

    SELECT *
    FROM dbo.sync_chunk_execution
    WHERE chunk_execution_id = @chunk_execution_id;
END
GO
