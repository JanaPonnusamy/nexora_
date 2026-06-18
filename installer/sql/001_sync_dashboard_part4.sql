SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_Dashboard_GetManualTriggers
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetManualTriggers', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetManualTriggers;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetManualTriggers
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        mt.trigger_id,

        s.store_id,
        s.store_code,
        s.store_name,

        mt.trigger_type,

        mt.requested_by,

        ru.username AS requested_by_username,

        mt.requested_at,

        mt.approval_status,

        mt.approved_by,

        au.username AS approved_by_username,

        mt.approved_at

    FROM dbo.sync_manual_trigger mt

    INNER JOIN dbo.stores s
        ON mt.store_id = s.store_id

    LEFT JOIN dbo.users ru
        ON mt.requested_by = ru.user_id

    LEFT JOIN dbo.users au
        ON mt.approved_by = au.user_id

    WHERE mt.tenant_id = @tenant_id

    ORDER BY
        mt.requested_at DESC,
        mt.trigger_id DESC;
END;
GO

/* ============================================================
   sp_Dashboard_GetApprovalQueue
   ============================================================ */

IF OBJECT_ID('dbo.sp_Dashboard_GetApprovalQueue', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_Dashboard_GetApprovalQueue;
GO

CREATE PROCEDURE dbo.sp_Dashboard_GetApprovalQueue
(
    @tenant_id UNIQUEIDENTIFIER
)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        mt.trigger_id,

        mt.store_id,

        s.store_code,

        s.store_name,

        mt.trigger_type,

        mt.requested_by,

        u.username AS requested_by_username,

        u.first_name,

        u.last_name,

        mt.requested_at,

        mt.approval_status,

        aw.workflow_name,

        aw.approver_role,

        aw.approval_required,

        DATEDIFF
        (
            MINUTE,
            mt.requested_at,
            GETDATE()
        ) AS pending_minutes

    FROM dbo.sync_manual_trigger mt

    INNER JOIN dbo.stores s
        ON mt.store_id = s.store_id

    LEFT JOIN dbo.users u
        ON mt.requested_by = u.user_id

    LEFT JOIN dbo.sync_approval_workflow aw
        ON aw.tenant_id = mt.tenant_id
       AND aw.is_active = 1

    WHERE
        mt.tenant_id = @tenant_id
        AND mt.approval_status = 'PENDING'

    ORDER BY
        mt.requested_at ASC,
        mt.trigger_id ASC;
END;
GO