SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_SaveStoreInfo
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_SaveStoreInfo', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_SaveStoreInfo;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_SaveStoreInfo
(
    @onboarding_id BIGINT,

    @tenant_id UNIQUEIDENTIFIER,

    @store_code VARCHAR(50),
    @store_name VARCHAR(200),

    @store_abbreviation VARCHAR(50),

    @gst_number VARCHAR(100) = NULL,
    @drug_license_no VARCHAR(100) = NULL,

    @address1 VARCHAR(500) = NULL,
    @address2 VARCHAR(500) = NULL,

    @city VARCHAR(100) = NULL,
    @state VARCHAR(100) = NULL,
    @country VARCHAR(100) = NULL,
    @pincode VARCHAR(20) = NULL,

    @contact_person VARCHAR(200) = NULL,
    @contact_mobile VARCHAR(50) = NULL,
    @contact_email VARCHAR(200) = NULL
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
        THROW 58101, 'Invalid onboarding session.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.tenants
        WHERE tenant_id = @tenant_id
          AND is_active = 1
    )
    BEGIN
        THROW 58102, 'Tenant not found.', 1;
    END;

    IF NULLIF(LTRIM(RTRIM(@store_code)), '') IS NULL
    BEGIN
        THROW 58103, 'Store Code is required.', 1;
    END;

    IF NULLIF(LTRIM(RTRIM(@store_name)), '') IS NULL
    BEGIN
        THROW 58104, 'Store Name is required.', 1;
    END;

    IF NULLIF(LTRIM(RTRIM(@store_abbreviation)), '') IS NULL
    BEGIN
        THROW 58105, 'Store Abbreviation is required.', 1;
    END;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE tenant_id = @tenant_id
          AND store_code = @store_code
    )
    BEGIN
        THROW 58106, 'Store Code already exists within tenant.', 1;
    END;

    DECLARE @store_id UNIQUEIDENTIFIER;

    SET @store_id = NEWID();

    INSERT INTO dbo.stores
    (
        store_id,
        tenant_id,
        store_code,
        store_name,
        is_active,
        created_at
    )
    VALUES
    (
        @store_id,
        @tenant_id,
        @store_code,
        @store_name,
        1,
        GETDATE()
    );

    UPDATE dbo.stores
    SET
        store_abbreviation = @store_abbreviation,
        gst_number = @gst_number,
        drug_license_no = @drug_license_no,

        address1 = @address1,
        address2 = @address2,

        city = @city,
        state = @state,
        country = @country,
        pincode = @pincode,

        contact_person = @contact_person,
        contact_mobile = @contact_mobile,
        contact_email = @contact_email,

        updated_at = GETDATE()
    WHERE store_id = @store_id;

    UPDATE dbo.store_onboarding_log
    SET
        store_id = @store_id,
        onboarding_status = 'STORE_INFO_SAVED'
    WHERE onboarding_id = @onboarding_id;

    SELECT
        s.store_id,
        s.tenant_id,
        s.store_code,
        s.store_name,

        s.store_abbreviation,
        s.gst_number,
        s.drug_license_no,

        s.address1,
        s.address2,
        s.city,
        s.state,
        s.country,
        s.pincode,

        s.contact_person,
        s.contact_mobile,
        s.contact_email,

        s.is_active,
        s.created_at
    FROM dbo.stores s
    WHERE s.store_id = @store_id;
END;
GO