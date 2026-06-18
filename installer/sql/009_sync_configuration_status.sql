SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncConfig_GetStatus
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncConfig_GetStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncConfig_GetStatus;
GO

CREATE PROCEDURE dbo.sp_SyncConfig_GetStatus
(
    @config_id BIGINT
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.sync_configuration
        WHERE config_id = @config_id
    )
        THROW 60801, 'Sync configuration not found.', 1;

    SELECT
        sc.config_id,
        sc.tenant_id,
        t.tenant_code,
        t.tenant_name,

        sc.config_name,
        sc.is_active,

        sc.created_at,
        sc.created_by,
        sc.updated_at,
        sc.updated_by,

        sch.schedule_id,
        sch.schedule_name,
        sch.schedule_type,
        sch.start_time,
        sch.is_enabled,

        rr.rule_id AS retry_rule_id,
        rr.max_retry_count,
        rr.retry_interval_minutes,

        cr.rule_id AS chunk_rule_id,
        cr.chunk_size,
        cr.parallel_chunks,

        rc.cycle_id,
        rc.cycle_name,
        rc.refresh_type,
        rc.refresh_interval_minutes,

        aw.workflow_id,
        aw.workflow_name,
        aw.approval_required,
        aw.approver_role,

        (
            SELECT COUNT(*)
            FROM dbo.sync_store_selection sss
            WHERE sss.config_id = sc.config_id
              AND sss.is_selected = 1
        ) AS selected_store_count,

        (
            SELECT COUNT(*)
            FROM dbo.sync_manual_trigger smt
            WHERE smt.tenant_id = sc.tenant_id
              AND smt.approval_status = 'PENDING'
        ) AS pending_trigger_count,

        (
            SELECT COUNT(*)
            FROM dbo.sync_manual_trigger smt
            WHERE smt.tenant_id = sc.tenant_id
              AND smt.approval_status = 'APPROVED'
        ) AS approved_trigger_count,

        (
            SELECT COUNT(*)
            FROM dbo.sync_manual_trigger smt
            WHERE smt.tenant_id = sc.tenant_id
              AND smt.approval_status = 'REJECTED'
        ) AS rejected_trigger_count

    FROM dbo.sync_configuration sc

    INNER JOIN dbo.tenants t
        ON sc.tenant_id = t.tenant_id

    LEFT JOIN dbo.sync_schedule sch
        ON sch.tenant_id = sc.tenant_id

    LEFT JOIN dbo.sync_retry_rules rr
        ON rr.tenant_id = sc.tenant_id
       AND rr.is_active = 1

    LEFT JOIN dbo.sync_chunk_rules cr
        ON cr.tenant_id = sc.tenant_id
       AND cr.is_active = 1

    LEFT JOIN dbo.sync_refresh_cycles rc
        ON rc.tenant_id = sc.tenant_id
       AND rc.is_active = 1

    LEFT JOIN dbo.sync_approval_workflow aw
        ON aw.tenant_id = sc.tenant_id
       AND aw.is_active = 1

    WHERE sc.config_id = @config_id;
END;
GO