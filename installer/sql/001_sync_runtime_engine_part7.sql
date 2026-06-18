IF OBJECT_ID('dbo.sp_Runtime_CompleteExecution', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_CompleteExecution
GO

CREATE PROCEDURE dbo.sp_Runtime_CompleteExecution
(
    @execution_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @completed_tables INT;
    DECLARE @failed_tables INT;
    DECLARE @total_tables INT;

    SELECT
        @total_tables = COUNT(*),
        @completed_tables = SUM(CASE WHEN chunk_status = 'COMPLETED' THEN 1 ELSE 0 END),
        @failed_tables = SUM(CASE WHEN chunk_status = 'FAILED' THEN 1 ELSE 0 END)
    FROM dbo.sync_chunk_execution
    WHERE execution_id = @execution_id;

    UPDATE dbo.sync_execution
    SET execution_status = 'COMPLETED',
        completed_at = GETDATE(),
        total_tables = ISNULL(@total_tables,0),
        completed_tables = ISNULL(@completed_tables,0),
        failed_tables = ISNULL(@failed_tables,0)
    WHERE execution_id = @execution_id;

    SELECT *
    FROM dbo.sync_execution
    WHERE execution_id = @execution_id;
END
GO

IF OBJECT_ID('dbo.sp_Runtime_FailExecution', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_FailExecution
GO

CREATE PROCEDURE dbo.sp_Runtime_FailExecution
(
    @execution_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @completed_tables INT;
    DECLARE @failed_tables INT;
    DECLARE @total_tables INT;

    SELECT
        @total_tables = COUNT(*),
        @completed_tables = SUM(CASE WHEN chunk_status = 'COMPLETED' THEN 1 ELSE 0 END),
        @failed_tables = SUM(CASE WHEN chunk_status = 'FAILED' THEN 1 ELSE 0 END)
    FROM dbo.sync_chunk_execution
    WHERE execution_id = @execution_id;

    UPDATE dbo.sync_execution
    SET execution_status = 'FAILED',
        completed_at = GETDATE(),
        total_tables = ISNULL(@total_tables,0),
        completed_tables = ISNULL(@completed_tables,0),
        failed_tables = ISNULL(@failed_tables,0)
    WHERE execution_id = @execution_id;

    SELECT *
    FROM dbo.sync_execution
    WHERE execution_id = @execution_id;
END
GO
