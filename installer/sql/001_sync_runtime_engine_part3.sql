IF OBJECT_ID('dbo.sp_Runtime_AcquireLock', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_AcquireLock;
GO

CREATE PROCEDURE dbo.sp_Runtime_AcquireLock
(
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,
    @table_name VARCHAR(200),
    @execution_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.sync_execution_lock
    (
        tenant_id,
        store_id,
        table_name,
        sync_id,
        lock_acquired_at,
        lock_expires_at,
        lock_status
    )
    VALUES
    (
        @tenant_id,
        @store_id,
        @table_name,
        @execution_id,
        GETDATE(),
        DATEADD(MINUTE,30,GETDATE()),
        'ACTIVE'
    );

    SELECT TOP 1 *
    FROM dbo.sync_execution_lock
    WHERE sync_id = @execution_id
      AND store_id = @store_id
      AND table_name = @table_name
    ORDER BY lock_acquired_at DESC;
END;
GO