/* =====================================================
   sync_configuration
===================================================== */

CREATE TABLE sync_configuration
(
    config_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    config_name VARCHAR(100) NOT NULL,

    is_active BIT NOT NULL DEFAULT(1),

    created_at DATETIME NOT NULL DEFAULT(GETDATE()),
    created_by UNIQUEIDENTIFIER NULL,

    updated_at DATETIME NULL,
    updated_by UNIQUEIDENTIFIER NULL
);

CREATE INDEX IX_sync_configuration_tenant
ON sync_configuration(tenant_id);


/* =====================================================
   sync_schedule
===================================================== */

CREATE TABLE sync_schedule
(
    schedule_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    schedule_name VARCHAR(100) NOT NULL,

    schedule_type VARCHAR(50) NOT NULL,

    start_time DATETIME NOT NULL,

    is_enabled BIT NOT NULL DEFAULT(1),

    created_at DATETIME NOT NULL DEFAULT(GETDATE())
);

CREATE INDEX IX_sync_schedule_tenant
ON sync_schedule(tenant_id);


/* =====================================================
   sync_manual_trigger
===================================================== */

CREATE TABLE sync_manual_trigger
(
    trigger_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    store_id UNIQUEIDENTIFIER NOT NULL,

    trigger_type VARCHAR(50) NOT NULL,

    requested_by UNIQUEIDENTIFIER NOT NULL,

    requested_at DATETIME NOT NULL DEFAULT(GETDATE()),

    approval_status VARCHAR(50) NOT NULL DEFAULT('PENDING'),

    approved_by UNIQUEIDENTIFIER NULL,

    approved_at DATETIME NULL
);

CREATE INDEX IX_sync_manual_trigger_tenant
ON sync_manual_trigger(tenant_id);

CREATE INDEX IX_sync_manual_trigger_store
ON sync_manual_trigger(store_id);


/* =====================================================
   sync_store_selection
===================================================== */

CREATE TABLE sync_store_selection
(
    id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    config_id BIGINT NOT NULL,

    store_id UNIQUEIDENTIFIER NOT NULL,

    is_selected BIT NOT NULL DEFAULT(1)
);

CREATE INDEX IX_sync_store_selection_tenant
ON sync_store_selection(tenant_id);

CREATE INDEX IX_sync_store_selection_config
ON sync_store_selection(config_id);


/* =====================================================
   sync_retry_rules
===================================================== */

CREATE TABLE sync_retry_rules
(
    rule_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    max_retry_count INT NOT NULL,

    retry_interval_minutes INT NOT NULL,

    is_active BIT NOT NULL DEFAULT(1)
);

CREATE INDEX IX_sync_retry_rules_tenant
ON sync_retry_rules(tenant_id);


/* =====================================================
   sync_chunk_rules
===================================================== */

CREATE TABLE sync_chunk_rules
(
    rule_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    chunk_size INT NOT NULL,

    parallel_chunks INT NOT NULL,

    is_active BIT NOT NULL DEFAULT(1)
);

CREATE INDEX IX_sync_chunk_rules_tenant
ON sync_chunk_rules(tenant_id);


/* =====================================================
   sync_refresh_cycles
===================================================== */

CREATE TABLE sync_refresh_cycles
(
    cycle_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    cycle_name VARCHAR(100) NOT NULL,

    refresh_type VARCHAR(50) NOT NULL,

    refresh_interval_minutes INT NOT NULL,

    is_active BIT NOT NULL DEFAULT(1)
);

CREATE INDEX IX_sync_refresh_cycles_tenant
ON sync_refresh_cycles(tenant_id);


/* =====================================================
   sync_approval_workflow
===================================================== */

CREATE TABLE sync_approval_workflow
(
    workflow_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,

    workflow_name VARCHAR(100) NOT NULL,

    approval_required BIT NOT NULL DEFAULT(1),

    approver_role VARCHAR(50) NOT NULL,

    is_active BIT NOT NULL DEFAULT(1)
);

CREATE INDEX IX_sync_approval_workflow_tenant
ON sync_approval_workflow(tenant_id);