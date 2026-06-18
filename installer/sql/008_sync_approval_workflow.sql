SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncApprovalWorkflow_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncApprovalWorkflow_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncApprovalWorkflow_Save;
GO

CREATE PROCEDURE dbo.sp_SyncApprovalWorkflow_Save
(
    @tenant_id UNIQUEIDENTIFIER,
    @workflow_name VARCHAR(100),
    @approval_required BIT,
    @approver_role VARCHAR(50),
    @is_active BIT = 1
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_id = @tenant_id
          AND is_active = 1
    )
        THROW 60701, 'Tenant not found.', 1;

    IF NULLIF(LTRIM(RTRIM(@workflow_name)), '') IS NULL
        THROW 60702, 'Workflow name is required.', 1;

    IF @approval_required = 1
       AND NULLIF(LTRIM(RTRIM(@approver_role)), '') IS NULL
        THROW 60703, 'Approver role is required when approval is enabled.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_approval_workflow
        WHERE tenant_id = @tenant_id
          AND workflow_name = @workflow_name
    )
    BEGIN
        UPDATE dbo.sync_approval_workflow
        SET
            approval_required = @approval_required,
            approver_role = @approver_role,
            is_active = @is_active
        WHERE tenant_id = @tenant_id
          AND workflow_name = @workflow_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.sync_approval_workflow
        (
            tenant_id,
            workflow_name,
            approval_required,
            approver_role,
            is_active
        )
        VALUES
        (
            @tenant_id,
            @workflow_name,
            @approval_required,
            @approver_role,
            @is_active
        );
    END;

    SELECT
        workflow_id,
        tenant_id,
        workflow_name,
        approval_required,
        approver_role,
        is_active
    FROM dbo.sync_approval_workflow
    WHERE tenant_id = @tenant_id
      AND workflow_name = @workflow_name;
END;
GO