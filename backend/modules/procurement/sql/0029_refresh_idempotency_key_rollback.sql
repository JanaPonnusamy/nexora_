/* Rollback 0029_refresh_idempotency_key.sql. Run manually against NEXORA_PLATFORM. */

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UX_procurement_refreshes_idempotency_key'
      AND object_id = OBJECT_ID('procurement.procurement_refreshes')
)
    DROP INDEX UX_procurement_refreshes_idempotency_key
        ON procurement.procurement_refreshes;
GO

IF COL_LENGTH('procurement.procurement_refreshes', 'idempotency_key') IS NOT NULL
    ALTER TABLE procurement.procurement_refreshes DROP COLUMN idempotency_key;
GO
