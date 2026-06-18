SET ANSI_NULLS ON;
GO

SET QUOTED_IDENTIFIER ON;
GO

/* ============================================================
   sync_execution_history
   ============================================================ */

IF OBJECT_ID('dbo.sync_execution_history', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.sync_execution_history
    (
        sync_id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NOT NULL,

        sync_mode VARCHAR(50) NOT NULL,

        sync_type VARCHAR(50) NULL,

        started_at DATETIME NOT NULL,

        completed_at DATETIME NULL,

        duration_seconds INT NULL,

        total_rows BIGINT NOT NULL DEFAULT(0),

        processed_rows BIGINT NOT NULL DEFAULT(0),

        failed_rows BIGINT NOT NULL DEFAULT(0),

        status VARCHAR(50) NOT NULL,

        triggered_by UNIQUEIDENTIFIER NULL,

        error_message NVARCHAR(MAX) NULL,

        created_at DATETIME NOT NULL DEFAULT(GETDATE())
    );
END;
GO

/* ============================================================
   sync_execution_details
   ============================================================ */

IF OBJECT_ID('dbo.sync_execution_details', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.sync_execution_details
    (
        detail_id BIGINT IDENTITY(1,1) PRIMARY KEY,

        sync_id BIGINT NOT NULL,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NOT NULL,

        table_name VARCHAR(200) NOT NULL,

        chunk_no INT NOT NULL,

        chunk_size INT NOT NULL,

        rows_processed BIGINT NOT NULL DEFAULT(0),

        rows_failed BIGINT NOT NULL DEFAULT(0),

        started_at DATETIME NOT NULL,

        completed_at DATETIME NULL,

        duration_seconds INT NULL,

        status VARCHAR(50) NOT NULL,

        error_message NVARCHAR(MAX) NULL,

        created_at DATETIME NOT NULL DEFAULT(GETDATE())
    );
END;
GO

/* ============================================================
   sync_dashboard_snapshot
   ============================================================ */

IF OBJECT_ID('dbo.sync_dashboard_snapshot', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.sync_dashboard_snapshot
    (
        snapshot_id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        total_stores INT NOT NULL DEFAULT(0),

        online_stores INT NOT NULL DEFAULT(0),

        offline_stores INT NOT NULL DEFAULT(0),

        running_syncs INT NOT NULL DEFAULT(0),

        failed_syncs INT NOT NULL DEFAULT(0),

        pending_approvals INT NOT NULL DEFAULT(0),

        today_sync_count INT NOT NULL DEFAULT(0),

        data_processed_today BIGINT NOT NULL DEFAULT(0),

        snapshot_time DATETIME NOT NULL DEFAULT(GETDATE())
    );
END;
GO

/* ============================================================
   sync_execution_lock
   ============================================================ */

IF OBJECT_ID('dbo.sync_execution_lock', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.sync_execution_lock
    (
        lock_id BIGINT IDENTITY(1,1) PRIMARY KEY,

        tenant_id UNIQUEIDENTIFIER NOT NULL,

        store_id UNIQUEIDENTIFIER NOT NULL,

        table_name VARCHAR(200) NOT NULL,

        sync_id BIGINT NULL,

        lock_acquired_at DATETIME NOT NULL,

        lock_expires_at DATETIME NOT NULL,

        lock_status VARCHAR(50) NOT NULL,

        acquired_by UNIQUEIDENTIFIER NULL
    );
END;
GO

/* ============================================================
   FOREIGN KEYS
   ============================================================ */

IF NOT EXISTS
(
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_sync_execution_details_history'
)
BEGIN
    ALTER TABLE dbo.sync_execution_details
    ADD CONSTRAINT FK_sync_execution_details_history
    FOREIGN KEY (sync_id)
    REFERENCES dbo.sync_execution_history(sync_id);
END;
GO

/* ============================================================
   INDEXES
   ============================================================ */

CREATE NONCLUSTERED INDEX IX_sync_execution_history_store
ON dbo.sync_execution_history(store_id, status);
GO

CREATE NONCLUSTERED INDEX IX_sync_execution_history_started
ON dbo.sync_execution_history(started_at);
GO

CREATE NONCLUSTERED INDEX IX_sync_execution_details_sync
ON dbo.sync_execution_details(sync_id);
GO

CREATE NONCLUSTERED INDEX IX_sync_execution_details_table
ON dbo.sync_execution_details(table_name, status);
GO

CREATE NONCLUSTERED INDEX IX_sync_dashboard_snapshot_tenant
ON dbo.sync_dashboard_snapshot(tenant_id, snapshot_time);
GO

CREATE NONCLUSTERED INDEX IX_sync_execution_lock_store
ON dbo.sync_execution_lock(store_id, lock_status);
GO