-- NMV Store Integration -- additive HO-side tables.
--
-- These live in the OrderNMC (legacy) database, NOT NEXORA_PLATFORM, on
-- purpose: an inbound order-result / uplink write and its idempotency record
-- must commit in the SAME transaction as the OrderManagement / POS data they
-- guard. Co-locating them is what makes "a retry after HO already committed
-- applies nothing twice" true rather than best-effort.
--
-- Everything here is additive. No existing legacy table is renamed, retyped, or
-- has its status semantics changed. Rollback = drop these three tables.
--
-- Batches are separated by a line that begins with GO (see ensure_schema()).

-- Per-(store, entity) sync watermark. entity is a logical name: an uplink POS
-- table ('ProductSaleInformation', 'Products', ...), or a downlink entity
-- ('OrderManagement', 'OrderSuppliers', ...). strategy records how the
-- watermark is interpreted so the agent and HO never disagree on its meaning.
IF OBJECT_ID('dbo.nmv_sync_watermark', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.nmv_sync_watermark (
        store_name     NVARCHAR(100) NOT NULL,
        entity         NVARCHAR(100) NOT NULL,
        strategy       NVARCHAR(30)  NOT NULL
            CONSTRAINT DF_nmv_wm_strategy DEFAULT ('id'),
        watermark_num  BIGINT        NULL,
        watermark_str  NVARCHAR(200) NULL,
        updated_at     DATETIME2(0)  NOT NULL
            CONSTRAINT DF_nmv_wm_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_nmv_sync_watermark PRIMARY KEY (store_name, entity)
    );
END;
GO

-- Inbound-message idempotency ledger. A client-generated message_id is recorded
-- the first time it is processed; a replay returns the stored response_json and
-- applies nothing. Also the write-path replay-protection record.
IF OBJECT_ID('dbo.nmv_sync_message', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.nmv_sync_message (
        message_id    UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT PK_nmv_sync_message PRIMARY KEY,
        store_name    NVARCHAR(100) NOT NULL,
        direction     NVARCHAR(10)  NOT NULL,          -- 'up' | 'down'
        kind          NVARCHAR(40)  NOT NULL,          -- 'uplink' | 'order_results' | ...
        received_at   DATETIME2(0)  NOT NULL
            CONSTRAINT DF_nmv_msg_received DEFAULT SYSUTCDATETIME(),
        status        NVARCHAR(20)  NOT NULL
            CONSTRAINT DF_nmv_msg_status DEFAULT ('applied'),
        rows_in       INT           NULL,
        rows_applied  INT           NULL,
        error         NVARCHAR(1000) NULL,
        response_json NVARCHAR(MAX) NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.nmv_sync_message')
      AND name = 'IX_nmv_sync_message_store_received'
)
BEGIN
    CREATE INDEX IX_nmv_sync_message_store_received
        ON dbo.nmv_sync_message(store_name, received_at DESC);
END;
GO

-- Per-message correlation + audit. No credentials/tokens are ever stored here;
-- only counts, timing, the correlation ids and an outcome.
IF OBJECT_ID('dbo.nmv_sync_audit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.nmv_sync_audit (
        audit_id    BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_nmv_sync_audit PRIMARY KEY,
        store_name  NVARCHAR(100) NOT NULL,
        device_id   NVARCHAR(100) NULL,
        message_id  UNIQUEIDENTIFIER NULL,
        entity      NVARCHAR(100) NULL,
        direction   NVARCHAR(10)  NOT NULL,
        rows        INT           NULL,
        started_at  DATETIME2(0)  NOT NULL
            CONSTRAINT DF_nmv_audit_started DEFAULT SYSUTCDATETIME(),
        ended_at    DATETIME2(0)  NULL,
        status      NVARCHAR(20)  NOT NULL
            CONSTRAINT DF_nmv_audit_status DEFAULT ('ok'),
        detail      NVARCHAR(1000) NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.nmv_sync_audit')
      AND name = 'IX_nmv_sync_audit_store_started'
)
BEGIN
    CREATE INDEX IX_nmv_sync_audit_store_started
        ON dbo.nmv_sync_audit(store_name, started_at DESC);
END;
GO
