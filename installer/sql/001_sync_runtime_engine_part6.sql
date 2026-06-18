IF OBJECT_ID('dbo.sp_Runtime_CheckApproval', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_CheckApproval
GO

CREATE PROCEDURE dbo.sp_Runtime_CheckApproval
(
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP 1
           trigger_id,
           tenant_id,
           store_id,
           trigger_type,
           requested_by,
           requested_at,
           approval_status,
           approved_by,
           approved_at
    FROM dbo.sync_manual_trigger
    WHERE tenant_id = @tenant_id
      AND store_id = @store_id
    ORDER BY requested_at DESC;
END
GO

IF OBJECT_ID('dbo.sp_Runtime_UpdateApproval', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Runtime_UpdateApproval
GO

CREATE PROCEDURE dbo.sp_Runtime_UpdateApproval
(
    @trigger_id BIGINT,
    @approval_status VARCHAR(50),
    @approved_by UNIQUEIDENTIFIER = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sync_manual_trigger
    SET approval_status = @approval_status,
        approved_by = @approved_by,
        approved_at = GETDATE()
    WHERE trigger_id = @trigger_id;

    SELECT *
    FROM dbo.sync_manual_trigger
    WHERE trigger_id = @trigger_id;
END
GO
