SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_SaveSyncSettings
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_SaveSyncSettings', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_SaveSyncSettings;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_SaveSyncSettings
(
    @onboarding_id BIGINT,
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,

    @sync_enabled BIT,
    @initial_sync_type VARCHAR(20),
    @schedule_enabled BIT
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
        THROW 58501, 'Invalid onboarding session.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND tenant_id = @tenant_id
    )
    BEGIN
        THROW 58502, 'Store not found.', 1;
    END;

    IF @initial_sync_type NOT IN ('FULL','INCREMENTAL')
    BEGIN
        THROW 58503, 'Invalid Initial Sync Type.', 1;
    END;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.store_sync_settings
        WHERE tenant_id = @tenant_id
          AND store_id = @store_id
    )
    BEGIN

        UPDATE dbo.store_sync_settings
        SET
            sync_enabled = @sync_enabled,
            initial_sync_type = @initial_sync_type,
            schedule_enabled = @schedule_enabled
        WHERE tenant_id = @tenant_id
          AND store_id = @store_id;

    END
    ELSE
    BEGIN

        INSERT INTO dbo.store_sync_settings
        (
            tenant_id,
            store_id,
            sync_enabled,
            initial_sync_type,
            schedule_enabled,
            created_at
        )
        VALUES
        (
            @tenant_id,
            @store_id,
            @sync_enabled,
            @initial_sync_type,
            @schedule_enabled,
            GETDATE()
        );

    END;

    UPDATE dbo.store_onboarding_log
    SET
        onboarding_status = 'SYNC_CONFIGURATION_COMPLETED'
    WHERE onboarding_id = @onboarding_id;

    SELECT
        id,
        tenant_id,
        store_id,
        sync_enabled,
        initial_sync_type,
        schedule_enabled,
        created_at
    FROM dbo.store_sync_settings
    WHERE tenant_id = @tenant_id
      AND store_id = @store_id;
END;
GO