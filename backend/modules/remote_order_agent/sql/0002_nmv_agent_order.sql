-- Remote Order Agent order lifecycle control tables (OrderNMC / central).
-- Kept additive, beside dbo.nmv_sync_watermark / nmv_sync_message / nmv_sync_audit.

-- Per-order delivery acknowledgement: an order is "pending" for the device until
-- it has an APPLIED (or REJECTED) ack row for its current version.
IF OBJECT_ID('dbo.nmv_order_ack', 'U') IS NULL
CREATE TABLE dbo.nmv_order_ack (
    store_name          NVARCHAR(200) NOT NULL,
    order_id            BIGINT NOT NULL,
    version             INT NOT NULL,
    state               NVARCHAR(20) NOT NULL,          -- APPLIED | REJECTED | DEFERRED
    payload_sha256      CHAR(64) NULL,
    applied_line_count  INT NULL,
    reason_code         NVARCHAR(50) NULL,
    reason              NVARCHAR(500) NULL,
    acked_at            DATETIME2 NOT NULL CONSTRAINT DF_nmv_order_ack_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_nmv_order_ack PRIMARY KEY (store_name, order_id, version)
);
GO

-- Append-only result-push dedup ledger. HO dedup key = (store_id, queue_epoch,
-- change_id); a row here means that change was already applied, so a retry is a
-- "duplicate", never a double-apply.
IF OBJECT_ID('dbo.nmv_agent_result_ledger', 'U') IS NULL
CREATE TABLE dbo.nmv_agent_result_ledger (
    store_id     NVARCHAR(64) NOT NULL,
    queue_epoch  NVARCHAR(64) NOT NULL,
    change_id    BIGINT NOT NULL,
    operation    NVARCHAR(1) NULL,
    order_id     BIGINT NULL,
    product_code NVARCHAR(50) NULL,
    applied_at   DATETIME2 NOT NULL CONSTRAINT DF_nmv_agent_result_ledger_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_nmv_agent_result_ledger PRIMARY KEY (store_id, queue_epoch, change_id)
);
GO
