/* ============================================
   sync_execution
============================================ */

CREATE TABLE sync_execution
(
    execution_id UNIQUEIDENTIFIER NOT NULL
        DEFAULT NEWID()
        PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    store_id UNIQUEIDENTIFIER NOT NULL,

    execution_type VARCHAR(50) NOT NULL,

    sync_mode VARCHAR(50) NOT NULL,

    execution_status VARCHAR(50) NOT NULL,

    started_at DATETIME NOT NULL DEFAULT GETDATE(),

    completed_at DATETIME NULL,

    total_tables INT NOT NULL DEFAULT 0,

    completed_tables INT NOT NULL DEFAULT 0,

    failed_tables INT NOT NULL DEFAULT 0,

    initiated_by UNIQUEIDENTIFIER NULL
);

CREATE INDEX IX_sync_execution_tenant
ON sync_execution(tenant_id);

CREATE INDEX IX_sync_execution_store
ON sync_execution(store_id);

CREATE INDEX IX_sync_execution_status
ON sync_execution(execution_status);

/* ============================================
   sync_chunk_execution
============================================ */

CREATE TABLE sync_chunk_execution
(
    chunk_execution_id BIGINT IDENTITY(1,1)
        PRIMARY KEY,

    execution_id UNIQUEIDENTIFIER NOT NULL,

    table_name VARCHAR(200) NOT NULL,

    chunk_no INT NOT NULL,

    chunk_status VARCHAR(50) NOT NULL,

    rows_processed BIGINT NOT NULL DEFAULT 0,

    retry_count INT NOT NULL DEFAULT 0,

    started_at DATETIME NULL,

    completed_at DATETIME NULL,

    error_message NVARCHAR(MAX) NULL
);

CREATE INDEX IX_sync_chunk_execution_exec
ON sync_chunk_execution(execution_id);

CREATE INDEX IX_sync_chunk_execution_status
ON sync_chunk_execution(chunk_status);


/* ============================================
   sync_execution_audit
============================================ */

CREATE TABLE sync_execution_audit
(
    audit_id BIGINT IDENTITY(1,1)
        PRIMARY KEY,

    execution_id UNIQUEIDENTIFIER NOT NULL,

    action_name VARCHAR(200) NOT NULL,

    action_time DATETIME NOT NULL
        DEFAULT GETDATE(),

    message NVARCHAR(MAX) NULL
);

CREATE INDEX IX_sync_execution_audit_exec
ON sync_execution_audit(execution_id);



CREATE TABLE sync_table_registry
(
    table_id BIGINT IDENTITY(1,1)
        PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    table_name VARCHAR(200) NOT NULL,

    sync_order INT NOT NULL,

    chunk_enabled BIT NOT NULL DEFAULT 1,

    refresh_enabled BIT NOT NULL DEFAULT 1,

    is_active BIT NOT NULL DEFAULT 1
);
