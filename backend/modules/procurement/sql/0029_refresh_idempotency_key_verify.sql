/* Verify 0029_refresh_idempotency_key.sql. Run manually against NEXORA_PLATFORM. */

SELECT COL_LENGTH('procurement.procurement_refreshes', 'idempotency_key') AS has_idempotency_key;
-- Expect NOT NULL (column exists).

SELECT COUNT(*) AS index_exists
FROM sys.indexes
WHERE name = 'UX_procurement_refreshes_idempotency_key'
  AND object_id = OBJECT_ID('procurement.procurement_refreshes');
-- Expect 1.

SELECT tenant_id, cycle_id, idempotency_key, COUNT(*) AS n
FROM procurement.procurement_refreshes
WHERE idempotency_key IS NOT NULL
GROUP BY tenant_id, cycle_id, idempotency_key
HAVING COUNT(*) > 1;
-- Expect 0 rows — the filtered unique index should already prevent this.
