SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_SaveBranchMapping
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_SaveBranchMapping', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_SaveBranchMapping;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_SaveBranchMapping
(
    @onboarding_id BIGINT,
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,

    @branch_codes VARCHAR(MAX),

    @mapping_source VARCHAR(20)
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
        THROW 58401, 'Invalid onboarding session.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
          AND tenant_id = @tenant_id
    )
    BEGIN
        THROW 58402, 'Store not found.', 1;
    END;

    IF NULLIF(LTRIM(RTRIM(@branch_codes)), '') IS NULL
    BEGIN
        THROW 58403, 'Branch codes are required.', 1;
    END;

    IF @mapping_source NOT IN ('MANUAL', 'DATABASE')
    BEGIN
        THROW 58404, 'Invalid mapping source.', 1;
    END;

    UPDATE dbo.stores
    SET
        branch_codes = @branch_codes,
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    UPDATE dbo.store_onboarding_log
    SET
        onboarding_status = 'BRANCH_MAPPING_COMPLETED',
        remarks =
            ISNULL(remarks, '') +
            CHAR(13) + CHAR(10) +
            'Branch Mapping Source: ' +
            @mapping_source +
            ' | Saved At: ' +
            CONVERT(VARCHAR(19), GETDATE(), 120)
    WHERE onboarding_id = @onboarding_id;

    SELECT
        s.store_id,
        s.tenant_id,
        s.store_code,
        s.store_name,
        s.branch_codes,
        @mapping_source AS mapping_source,
        s.updated_at
    FROM dbo.stores s
    WHERE s.store_id = @store_id;
END;
GO