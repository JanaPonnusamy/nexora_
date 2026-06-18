CREATE TABLE store_onboarding_log
(
    onboarding_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NULL,

    onboarding_status VARCHAR(50) NOT NULL,

    started_by UNIQUEIDENTIFIER NULL,
    started_at DATETIME NOT NULL DEFAULT GETDATE(),

    completed_at DATETIME NULL,

    remarks NVARCHAR(MAX) NULL
);

CREATE TABLE store_connection_test_log
(
    id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NOT NULL,

    server_name VARCHAR(500) NULL,
    database_name VARCHAR(200) NULL,

    test_status VARCHAR(50) NOT NULL,

    test_message NVARCHAR(MAX) NULL,

    tested_by UNIQUEIDENTIFIER NULL,
    tested_at DATETIME NOT NULL DEFAULT GETDATE()
);

CREATE TABLE store_agent_registry
(
    agent_id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NOT NULL,

    agent_version VARCHAR(50) NULL,

    connection_type VARCHAR(50) NULL,

    installed_at DATETIME NULL,

    last_heartbeat DATETIME NULL,

    connection_status VARCHAR(50) NULL,

    is_active BIT NOT NULL DEFAULT 1
);


CREATE TABLE store_sync_settings
(
    id BIGINT IDENTITY(1,1) PRIMARY KEY,

    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NOT NULL,

    sync_enabled BIT NOT NULL DEFAULT 1,

    initial_sync_type VARCHAR(20) NOT NULL DEFAULT 'FULL',

    schedule_enabled BIT NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT GETDATE()
);