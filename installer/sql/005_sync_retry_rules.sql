SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncRetryRule_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncRetryRule_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncRetryRule_Save;
GO

CREATE PROCEDURE dbo.sp_SyncRetryRule_Save
(
    @tenant_id UNIQUEIDENTIFIER,
    @max_retry_count INT,
    @retry_interval_minutes INT,
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
        THROW 60401, 'Tenant not found.', 1;

    IF @max_retry_count < 0
        THROW 60402, 'Max retry count must be zero or greater.', 1;

    IF @retry_interval_minutes <= 0
        THROW 60403, 'Retry interval must be greater than zero.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_retry_rules
        WHERE tenant_id = @tenant_id
    )
    BEGIN
        UPDATE dbo.sync_retry_rules
        SET
            max_retry_count = @max_retry_count,
            retry_interval_minutes = @retry_interval_minutes,
            is_active = @is_active
        WHERE tenant_id = @tenant_id;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.sync_retry_rules
        (
            tenant_id,
            max_retry_count,
            retry_interval_minutes,
            is_active
        )
        VALUES
        (
            @tenant_id,
            @max_retry_count,
            @retry_interval_minutes,
            @is_active
        );
    END;

    SELECT
        rule_id,
        tenant_id,
        max_retry_count,
        retry_interval_minutes,
        is_active
    FROM dbo.sync_retry_rules
    WHERE tenant_id = @tenant_id;
END;
GO