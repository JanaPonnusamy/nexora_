/*  NMV integration — additive install (idempotent).
    Run:  sqlcmd -S "DESKTOP-2\SQLEXPRESSORDER" -E -b -v DB=OrderNMC -i 001_nmv_integration_install.sql
    Changes NO existing table, column, key or status code. Adds:
      nmv_integration_store, nmv_change_queue, nmv_order_inbox, nmv_sync_state, nmv_sync_audit,
      trigger trg_nmv_OrderManagement_track on dbo.OrderManagement.
    Rollback: 001_nmv_integration_rollback.sql
*/
:on error exit
SET NOCOUNT ON;
USE [$(DB)];
GO
IF OBJECT_ID('dbo.OrderManagement','U') IS NULL
    RAISERROR('dbo.OrderManagement not found - wrong database?', 16, 1);
GO

/* ---------- which stores are integration-managed (read by VB guards and the trigger) ---------- */
IF OBJECT_ID('dbo.nmv_integration_store','U') IS NULL
CREATE TABLE dbo.nmv_integration_store (
    StoreName       nvarchar(200) NOT NULL CONSTRAINT PK_nmv_integration_store PRIMARY KEY,
    StoreCode       float         NULL,
    IsManaged       bit           NOT NULL CONSTRAINT DF_nmv_integration_store_IsManaged DEFAULT (1),
    AllowWebExport  bit           NOT NULL CONSTRAINT DF_nmv_integration_store_AllowWebExport DEFAULT (0),
    ManagedSince    datetime      NOT NULL CONSTRAINT DF_nmv_integration_store_ManagedSince DEFAULT (GETDATE()),
    Note            nvarchar(400) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM dbo.nmv_integration_store WHERE StoreName = N'NMV')
    INSERT INTO dbo.nmv_integration_store (StoreName, StoreCode, IsManaged, AllowWebExport, Note)
    VALUES (N'NMV', 10, 1, 0, N'Orders managed by HO/Nexora via NMVSyncAgent');
GO

/* ---------- persistent outbox of user edits ---------- */
IF OBJECT_ID('dbo.nmv_change_queue','U') IS NULL
CREATE TABLE dbo.nmv_change_queue (
    change_id               bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_nmv_change_queue PRIMARY KEY,
    captured_at             datetimeoffset(3) NOT NULL CONSTRAINT DF_nmv_change_queue_captured DEFAULT (SYSDATETIMEOFFSET()),
    operation               char(1)        NOT NULL,          -- I / U / D
    store_name              nvarchar(200)  NULL,
    order_id                bigint         NULL,
    product_code            float          NULL,
    old_order_qty           float NULL,  new_order_qty        float NULL,
    old_or_qty              float NULL,  new_or_qty           float NULL,
    old_qtycheck            int   NULL,  new_qtycheck         int   NULL,
    old_remarks             nvarchar(200) NULL, new_remarks          nvarchar(200) NULL,
    old_or_supplier         nvarchar(200) NULL, new_or_supplier      nvarchar(200) NULL,
    old_or_supplier_code    nvarchar(200) NULL, new_or_supplier_code nvarchar(200) NULL,
    old_status              nvarchar(200) NULL, new_status           nvarchar(200) NULL,
    db_login                nvarchar(128) NOT NULL CONSTRAINT DF_nmv_change_queue_login DEFAULT (SUSER_SNAME()),
    host_name               nvarchar(128) NULL     CONSTRAINT DF_nmv_change_queue_host  DEFAULT (HOST_NAME()),
    app_name                nvarchar(128) NULL     CONSTRAINT DF_nmv_change_queue_app   DEFAULT (APP_NAME()),
    sync_state              varchar(12)   NOT NULL CONSTRAINT DF_nmv_change_queue_state DEFAULT ('PENDING'),
                                                    -- PENDING | ACKED | REJECTED
    attempts                int           NOT NULL CONSTRAINT DF_nmv_change_queue_attempts DEFAULT (0),
    next_attempt_at         datetimeoffset(3) NULL,
    last_attempt_at         datetimeoffset(3) NULL,
    last_error              nvarchar(1000) NULL,
    batch_id                uniqueidentifier NULL,
    acked_at                datetimeoffset(3) NULL,
    CONSTRAINT CK_nmv_change_queue_op    CHECK (operation IN ('I','U','D')),
    CONSTRAINT CK_nmv_change_queue_state CHECK (sync_state IN ('PENDING','ACKED','REJECTED'))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_nmv_change_queue_state' AND object_id = OBJECT_ID('dbo.nmv_change_queue'))
    CREATE INDEX IX_nmv_change_queue_state ON dbo.nmv_change_queue (sync_state, change_id) INCLUDE (next_attempt_at, order_id);
GO

/* ---------- received HO orders (idempotency) ---------- */
IF OBJECT_ID('dbo.nmv_order_inbox','U') IS NULL
CREATE TABLE dbo.nmv_order_inbox (
    order_id        bigint        NOT NULL,
    version         int           NOT NULL,
    payload_sha256  char(64)      NOT NULL,
    line_count      int           NOT NULL,
    state           varchar(12)   NOT NULL,   -- APPLIED | REJECTED | DEFERRED
    reason_code     varchar(40)   NULL,
    reason          nvarchar(1000) NULL,
    received_at     datetimeoffset(3) NOT NULL CONSTRAINT DF_nmv_order_inbox_received DEFAULT (SYSDATETIMEOFFSET()),
    applied_at      datetimeoffset(3) NULL,
    ack_state       varchar(12)   NOT NULL CONSTRAINT DF_nmv_order_inbox_ack DEFAULT ('PENDING'), -- PENDING | ACKED
    ack_attempts    int           NOT NULL CONSTRAINT DF_nmv_order_inbox_ackatt DEFAULT (0),
    acked_at        datetimeoffset(3) NULL,
    last_error      nvarchar(1000) NULL,
    CONSTRAINT PK_nmv_order_inbox PRIMARY KEY (order_id, version),
    CONSTRAINT CK_nmv_order_inbox_state CHECK (state IN ('APPLIED','REJECTED','DEFERRED')),
    CONSTRAINT CK_nmv_order_inbox_ack   CHECK (ack_state IN ('PENDING','ACKED'))
);
GO

/* ---------- watermarks / misc state ---------- */
IF OBJECT_ID('dbo.nmv_sync_state','U') IS NULL
CREATE TABLE dbo.nmv_sync_state (
    state_key   nvarchar(100) NOT NULL CONSTRAINT PK_nmv_sync_state PRIMARY KEY,
    state_value nvarchar(max) NULL,
    updated_at  datetimeoffset(3) NOT NULL CONSTRAINT DF_nmv_sync_state_updated DEFAULT (SYSDATETIMEOFFSET())
);
GO
IF NOT EXISTS (SELECT 1 FROM dbo.nmv_sync_state WHERE state_key = N'queue_epoch')
    INSERT INTO dbo.nmv_sync_state (state_key, state_value) VALUES (N'queue_epoch', CONVERT(nvarchar(36), NEWID()));
IF NOT EXISTS (SELECT 1 FROM dbo.nmv_sync_state WHERE state_key = N'schema_version')
    INSERT INTO dbo.nmv_sync_state (state_key, state_value) VALUES (N'schema_version', N'1');
GO

/* ---------- audit ---------- */
IF OBJECT_ID('dbo.nmv_sync_audit','U') IS NULL
CREATE TABLE dbo.nmv_sync_audit (
    audit_id      bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_nmv_sync_audit PRIMARY KEY,
    at            datetimeoffset(3) NOT NULL CONSTRAINT DF_nmv_sync_audit_at DEFAULT (SYSDATETIMEOFFSET()),
    category      varchar(30)   NOT NULL,
    item          nvarchar(100) NULL,
    action        varchar(30)   NOT NULL,
    rows_examined int           NULL,
    rows_changed  int           NULL,
    outcome       varchar(12)   NOT NULL,   -- OK | FAILED | SKIPPED | REJECTED | DEFERRED
    duration_ms   int           NULL,
    detail        nvarchar(2000) NULL
);
GO

/* ---------- change-capture trigger ---------- */
IF OBJECT_ID('dbo.trg_nmv_OrderManagement_track','TR') IS NOT NULL
    DROP TRIGGER dbo.trg_nmv_OrderManagement_track;
GO
CREATE TRIGGER dbo.trg_nmv_OrderManagement_track
ON dbo.OrderManagement
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;   -- keeps VB ExecuteNonQuery row counts unchanged

    -- the agent marks its own sessions; its writes are not user edits (no echo, no recursion)
    IF SUBSTRING(ISNULL(CONTEXT_INFO(), 0x), 1, 9) = 0x4E4D565F4147454E54   -- 'NMV_AGENT'
        RETURN;

    DECLARE @hasIns bit = CASE WHEN EXISTS (SELECT 1 FROM inserted) THEN 1 ELSE 0 END;
    DECLARE @hasDel bit = CASE WHEN EXISTS (SELECT 1 FROM deleted)  THEN 1 ELSE 0 END;
    IF @hasIns = 0 AND @hasDel = 0 RETURN;

    -- Backstop for older VB builds without the NMV guard: the only VB code that deletes OrderManagement rows is
    -- "Process Order" (local regeneration). For an HO-managed store that would destroy the HO order, so refuse it.
    IF @hasIns = 0 AND @hasDel = 1
       AND EXISTS (SELECT 1 FROM deleted d JOIN dbo.nmv_integration_store s ON s.StoreName = d.StoreName AND s.IsManaged = 1)
    BEGIN
        RAISERROR('NMV integration: OrderManagement for this store is managed by HO. Local order regeneration (delete) is blocked.', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END;

    -- UPDATE that does not touch a tracked column: nothing to do
    IF @hasIns = 1 AND @hasDel = 1
       AND NOT (UPDATE(OrderQty) OR UPDATE(OrQty) OR UPDATE(Qtycheck) OR UPDATE(Remarks)
                OR UPDATE(OrSupplier) OR UPDATE(OrSupplierCode) OR UPDATE(Status))
        RETURN;

    INSERT INTO dbo.nmv_change_queue
        (operation, store_name, order_id, product_code,
         old_order_qty, new_order_qty, old_or_qty, new_or_qty, old_qtycheck, new_qtycheck,
         old_remarks, new_remarks, old_or_supplier, new_or_supplier,
         old_or_supplier_code, new_or_supplier_code, old_status, new_status)
    SELECT
        CASE WHEN d.StoreName IS NULL AND d.ProductCode IS NULL THEN 'I'
             WHEN i.StoreName IS NULL AND i.ProductCode IS NULL THEN 'D'
             ELSE 'U' END,
        COALESCE(i.StoreName, d.StoreName), COALESCE(i.OrderId, d.OrderId), COALESCE(i.ProductCode, d.ProductCode),
        d.OrderQty, i.OrderQty, d.OrQty, i.OrQty, d.Qtycheck, i.Qtycheck,
        d.Remarks, i.Remarks, d.OrSupplier, i.OrSupplier,
        d.OrSupplierCode, i.OrSupplierCode, d.Status, i.Status
    FROM inserted AS i
    FULL OUTER JOIN deleted AS d
         ON  d.StoreName   = i.StoreName
         AND d.ProductCode = i.ProductCode
         AND (d.OrderId = i.OrderId OR (d.OrderId IS NULL AND i.OrderId IS NULL))
    WHERE EXISTS (SELECT 1 FROM dbo.nmv_integration_store s
                  WHERE s.IsManaged = 1 AND s.StoreName = COALESCE(i.StoreName, d.StoreName))
      AND (   i.ProductCode IS NULL OR d.ProductCode IS NULL      -- insert / delete
           OR EXISTS (SELECT i.OrderQty, i.OrQty, i.Qtycheck, i.Remarks, i.OrSupplier, i.OrSupplierCode, i.Status
                      EXCEPT
                      SELECT d.OrderQty, d.OrQty, d.Qtycheck, d.Remarks, d.OrSupplier, d.OrSupplierCode, d.Status));
END;
GO

/* make sure the trigger fires last/first is irrelevant (only trigger on the table); report */
SELECT 'installed' AS result,
       (SELECT state_value FROM dbo.nmv_sync_state WHERE state_key = N'schema_version') AS schema_version,
       (SELECT COUNT(*) FROM dbo.nmv_integration_store WHERE IsManaged = 1) AS managed_stores,
       OBJECTPROPERTY(OBJECT_ID('dbo.trg_nmv_OrderManagement_track'), 'ExecIsTriggerDisabled') AS trigger_disabled;
GO
