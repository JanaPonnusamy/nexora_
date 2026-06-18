SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_GetStatus
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_GetStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_GetStatus;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_GetStatus
(
    @onboarding_id BIGINT
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.store_onboarding_log
        WHERE onboarding_id = @onboarding_id
    )
    BEGIN
        THROW 58701, 'Onboarding record not found.', 1;
    END;

    SELECT
        o.onboarding_id,
        o.tenant_id,
        t.tenant_code,
        t.tenant_name,

        o.store_id,
        s.store_code,
        s.store_name,

        o.onboarding_status,
        o.started_by,
        o.started_at,
        o.completed_at,
        o.remarks,

        CASE
            WHEN o.onboarding_status IN
            (
                'STARTED'
            )
            THEN 1

            WHEN o.onboarding_status IN
            (
                'STORE_INFO_SAVED'
            )
            THEN 2

            WHEN o.onboarding_status IN
            (
                'CONNECTION_VALIDATED'
            )
            THEN 3

            WHEN o.onboarding_status IN
            (
                'AGENT_REGISTERED'
            )
            THEN 4

            WHEN o.onboarding_status IN
            (
                'BRANCH_MAPPING_COMPLETED'
            )
            THEN 5

            WHEN o.onboarding_status IN
            (
                'SYNC_CONFIGURATION_COMPLETED'
            )
            THEN 6

            WHEN o.onboarding_status = 'COMPLETED'
            THEN 7

            ELSE 0
        END AS current_step,

        CASE
            WHEN o.onboarding_status = 'COMPLETED'
            THEN CAST(100 AS DECIMAL(5,2))

            WHEN o.onboarding_status = 'SYNC_CONFIGURATION_COMPLETED'
            THEN CAST(85.71 AS DECIMAL(5,2))

            WHEN o.onboarding_status = 'BRANCH_MAPPING_COMPLETED'
            THEN CAST(71.43 AS DECIMAL(5,2))

            WHEN o.onboarding_status = 'AGENT_REGISTERED'
            THEN CAST(57.14 AS DECIMAL(5,2))

            WHEN o.onboarding_status = 'CONNECTION_VALIDATED'
            THEN CAST(42.86 AS DECIMAL(5,2))

            WHEN o.onboarding_status = 'STORE_INFO_SAVED'
            THEN CAST(28.57 AS DECIMAL(5,2))

            WHEN o.onboarding_status = 'STARTED'
            THEN CAST(14.29 AS DECIMAL(5,2))

            ELSE CAST(0.00 AS DECIMAL(5,2))
        END AS completion_percentage,

        s.connection_status,
        s.connection_type,
        s.last_seen,

        ar.agent_version,
        ar.installed_at,
        ar.last_heartbeat,
        ar.connection_status AS agent_connection_status,

        ss.sync_enabled,
        ss.initial_sync_type,
        ss.schedule_enabled,

        ct.test_status,
        ct.test_message,
        ct.tested_at

    FROM dbo.store_onboarding_log o

    INNER JOIN dbo.tenants t
        ON o.tenant_id = t.tenant_id

    LEFT JOIN dbo.stores s
        ON o.store_id = s.store_id

    LEFT JOIN dbo.store_agent_registry ar
        ON o.store_id = ar.store_id
       AND ar.is_active = 1

    LEFT JOIN dbo.store_sync_settings ss
        ON o.store_id = ss.store_id

    OUTER APPLY
    (
        SELECT TOP 1
            test_status,
            test_message,
            tested_at
        FROM dbo.store_connection_test_log
        WHERE store_id = o.store_id
        ORDER BY tested_at DESC
    ) ct

    WHERE o.onboarding_id = @onboarding_id;
END;
GO