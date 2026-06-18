SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncStoreSelection_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncStoreSelection_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncStoreSelection_Save;
GO

CREATE PROCEDURE dbo.sp_SyncStoreSelection_Save
(
    @tenant_id UNIQUEIDENTIFIER,
    @config_id BIGINT,
    @store_id UNIQUEIDENTIFIER,
    @is_selected BIT
)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.sync_configuration
        WHERE config_id = @config_id
          AND tenant_id = @tenant_id
    )
        THROW 60301, 'Sync configuration not found.', 1;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND tenant_id = @tenant_id
    )
        THROW 60302, 'Store not found.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_store_selection
        WHERE tenant_id = @tenant_id
          AND config_id = @config_id
          AND store_id = @store_id
    )
    BEGIN
        UPDATE dbo.sync_store_selection
        SET
            is_selected = @is_selected
        WHERE tenant_id = @tenant_id
          AND config_id = @config_id
          AND store_id = @store_id;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.sync_store_selection
        (
            tenant_id,
            config_id,
            store_id,
            is_selected
        )
        VALUES
        (
            @tenant_id,
            @config_id,
            @store_id,
            @is_selected
        );
    END;

    SELECT
        ss.id,
        ss.tenant_id,
        ss.config_id,
        sc.config_name,
        ss.store_id,
        s.store_code,
        s.store_name,
        ss.is_selected
    FROM dbo.sync_store_selection ss
    INNER JOIN dbo.sync_configuration sc
        ON ss.config_id = sc.config_id
    INNER JOIN dbo.stores s
        ON ss.store_id = s.store_id
    WHERE ss.tenant_id = @tenant_id
      AND ss.config_id = @config_id
      AND ss.store_id = @store_id;
END;
GO