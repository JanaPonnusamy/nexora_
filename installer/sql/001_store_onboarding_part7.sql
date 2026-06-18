SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_Complete
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_Complete', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_Complete;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_Complete
(
    @onboarding_id BIGINT,
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,
    @completed_by UNIQUEIDENTIFIER,
    @remarks NVARCHAR(MAX) = NULL
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
        THROW 58601, 'Invalid onboarding session.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND tenant_id = @tenant_id
    )
    BEGIN
        THROW 58602, 'Store not found.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.store_agent_registry
        WHERE store_id = @store_id
          AND is_active = 1
    )
    BEGIN
        THROW 58603, 'Store Agent not registered.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.store_sync_settings
        WHERE store_id = @store_id
    )
    BEGIN
        THROW 58604, 'Sync Settings not configured.', 1;
    END;

    DECLARE @current_status VARCHAR(50);

    SELECT
        @current_status = onboarding_status
    FROM dbo.store_onboarding_log
    WHERE onboarding_id = @onboarding_id;

    IF @current_status = 'COMPLETED'
    BEGIN
        THROW 58605, 'Onboarding already completed.', 1;
    END;

    UPDATE dbo.store_onboarding_log
    SET
        onboarding_status = 'COMPLETED',
        completed_at = GETDATE(),
        remarks =
            CASE
                WHEN @remarks IS NULL
                    THEN remarks
                WHEN remarks IS NULL
                    THEN @remarks
                ELSE remarks + CHAR(13) + CHAR(10) + @remarks
            END
    WHERE onboarding_id = @onboarding_id;

    UPDATE dbo.stores
    SET
        connection_status = 'ACTIVE',
        last_seen = GETDATE(),
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    INSERT INTO dbo.global_audit_log
    (
        tenant_id,
        store_id,
        user_id,
        module_name,
        action_name,
        old_value,
        new_value,
        created_at
    )
    VALUES
    (
        @tenant_id,
        @store_id,
        @completed_by,
        'STORE_ONBOARDING',
        'COMPLETE',
        NULL,
        CONCAT
        (
            'Store Onboarding Completed. StoreId=',
            CONVERT(VARCHAR(36), @store_id)
        ),
        GETDATE()
    );

    SELECT
        o.onboarding_id,
        o.tenant_id,
        o.store_id,
        o.onboarding_status,
        o.started_by,
        o.started_at,
        o.completed_at,
        o.remarks,

        s.store_code,
        s.store_name,
        s.connection_status,
        s.last_seen,

        ss.sync_enabled,
        ss.initial_sync_type,
        ss.schedule_enabled

    FROM dbo.store_onboarding_log o
    INNER JOIN dbo.stores s
        ON o.store_id = s.store_id
    LEFT JOIN dbo.store_sync_settings ss
        ON s.store_id = ss.store_id
    WHERE o.onboarding_id = @onboarding_id;
END;
GO