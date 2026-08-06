/* Audit log for Stock Integrity repairs (dbo.stock_integrity_audit).
   One row per (store, batch) whose Stock was corrected from the live store
   database, plus the root-cause fix note. See modules/stock_integrity/README
   in the repository history: sync.sync_column_mapping.Batches.Stock was not
   flagged is_hash=1, so Stock-only changes were never detected/re-synced by
   the store agent. That flag was corrected separately; this table logs the
   one-time backlog repair for rows that went stale before the fix. */

IF OBJECT_ID('dbo.stock_integrity_audit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_integrity_audit
    (
        audit_id        UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NOT NULL,
        product_code    VARCHAR(50)      NOT NULL,
        batch_code      VARCHAR(50)      NOT NULL,
        old_stock       DECIMAL(18,2)    NULL,
        new_stock       DECIMAL(18,2)    NULL,
        difference      DECIMAL(18,2)    NULL,
        repair_status   VARCHAR(20)      NOT NULL,   /* REPAIRED / SKIPPED / FAILED */
        actor_user_id   UNIQUEIDENTIFIER NULL,
        detail          VARCHAR(500)     NULL,
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        PRIMARY KEY (audit_id)
    );
    CREATE INDEX IX_stock_integrity_audit_store ON dbo.stock_integrity_audit (store_id, created_at);
    CREATE INDEX IX_stock_integrity_audit_tenant ON dbo.stock_integrity_audit (tenant_id, created_at);
END
GO
