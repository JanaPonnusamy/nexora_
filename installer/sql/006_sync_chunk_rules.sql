SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sp_SyncChunkRule_Save
   ============================================================ */

IF OBJECT_ID('dbo.sp_SyncChunkRule_Save', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SyncChunkRule_Save;
GO

CREATE PROCEDURE dbo.sp_SyncChunkRule_Save
(
    @tenant_id UNIQUEIDENTIFIER,
    @chunk_size INT,
    @parallel_chunks INT,
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
        THROW 60501, 'Tenant not found.', 1;

    IF @chunk_size <= 0
        THROW 60502, 'Chunk size must be greater than zero.', 1;

    IF @parallel_chunks <= 0
        THROW 60503, 'Parallel chunks must be greater than zero.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM dbo.sync_chunk_rules
        WHERE tenant_id = @tenant_id
    )
    BEGIN
        UPDATE dbo.sync_chunk_rules
        SET
            chunk_size = @chunk_size,
            parallel_chunks = @parallel_chunks,
            is_active = @is_active
        WHERE tenant_id = @tenant_id;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.sync_chunk_rules
        (
            tenant_id,
            chunk_size,
            parallel_chunks,
            is_active
        )
        VALUES
        (
            @tenant_id,
            @chunk_size,
            @parallel_chunks,
            @is_active
        );
    END;

    SELECT
        rule_id,
        tenant_id,
        chunk_size,
        parallel_chunks,
        is_active
    FROM dbo.sync_chunk_rules
    WHERE tenant_id = @tenant_id;
END;
GO