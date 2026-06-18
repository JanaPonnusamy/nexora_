SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_StoreOnboarding_TestConnection
   ============================================================ */

IF OBJECT_ID('dbo.sp_StoreOnboarding_TestConnection', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_StoreOnboarding_TestConnection;
GO

CREATE PROCEDURE dbo.sp_StoreOnboarding_TestConnection
(
    @onboarding_id BIGINT,
    @tenant_id UNIQUEIDENTIFIER,
    @store_id UNIQUEIDENTIFIER,

    @server_name VARCHAR(500),
    @database_name VARCHAR(200),

    @authentication_type VARCHAR(50),

    @username VARCHAR(200) = NULL,
    @password_encrypted VARBINARY(MAX) = NULL,

    @tested_by UNIQUEIDENTIFIER,

    @server_reachable BIT,
    @database_exists BIT,
    @login_successful BIT,

    @test_message NVARCHAR(MAX) = NULL
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
        THROW 58201, 'Invalid onboarding session.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM dbo.stores
        WHERE store_id = @store_id
    )
    BEGIN
        THROW 58202, 'Store not found.', 1;
    END;

    DECLARE @test_status VARCHAR(50);

    IF @server_reachable = 1
       AND @database_exists = 1
       AND @login_successful = 1
    BEGIN
        SET @test_status = 'SUCCESS';
    END
    ELSE
    BEGIN
        SET @test_status = 'FAILED';
    END;

    INSERT INTO dbo.store_connection_test_log
    (
        tenant_id,
        store_id,
        server_name,
        database_name,
        test_status,
        test_message,
        tested_by,
        tested_at
    )
    VALUES
    (
        @tenant_id,
        @store_id,
        @server_name,
        @database_name,
        @test_status,
        @test_message,
        @tested_by,
        GETDATE()
    );

    UPDATE dbo.stores
    SET
        server_name = @server_name,
        database_name = @database_name,
        username = @username,
        password_encrypted = @password_encrypted,
        connection_status = @test_status,
        updated_at = GETDATE()
    WHERE store_id = @store_id;

    UPDATE dbo.store_onboarding_log
    SET
        onboarding_status =
            CASE
                WHEN @test_status = 'SUCCESS'
                    THEN 'CONNECTION_VALIDATED'
                ELSE 'CONNECTION_FAILED'
            END
    WHERE onboarding_id = @onboarding_id;

    SELECT
        l.id,
        l.tenant_id,
        l.store_id,
        l.server_name,
        l.database_name,
        l.test_status,
        l.test_message,
        l.tested_by,
        l.tested_at
    FROM dbo.store_connection_test_log l
    WHERE l.id = SCOPE_IDENTITY();
END;
GO