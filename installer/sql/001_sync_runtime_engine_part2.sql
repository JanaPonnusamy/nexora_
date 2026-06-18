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

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_execution_lock
        WHERE store_id = @store_id
          AND table_name = @table_name
          AND lock_status = 'ACTIVE'
          AND lock_expires_at > GETDATE()
    )
        THROW 61001, 'Lock already exists.', 1;

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

    SELECT *
    FROM dbo.sync_execution_lock
    WHERE lock_id = SCOPE_IDENTITY();
END;
GO

IF OBJECT_ID('dbo.sp_Runtime_ReleaseLock', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_ReleaseLock;
GO

CREATE PROCEDURE dbo.sp_Runtime_ReleaseLock
(
    @execution_id UNIQUEIDENTIFIER,
    @table_name VARCHAR(200)
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sync_execution_lock
    SET
        lock_status = 'RELEASED',
        lock_expires_at = GETDATE()
    WHERE sync_id = @execution_id
      AND table_name = @table_name;

    SELECT *
    FROM dbo.sync_execution_lock
    WHERE sync_id = @execution_id
      AND table_name = @table_name;
END;
GO

