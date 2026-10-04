-- Stock Client fleet management (Electron desktop client).
--
-- release != rollout: a RELEASE is an immutable, hash+signature-verified
-- package with a lifecycle (DRAFT -> APPROVED -> ROLLED_OUT -> RETIRED); a
-- DEPLOYMENT (rollout) targets a set of stores and must be explicitly
-- AUTHORIZED before any store acts on it. Per-store progress lives in
-- deployment_targets so one offline/failed store never blocks the others.
--
-- Mirrors the dbo.agent_* conventions (see modules/agent_ops) but models the
-- extra lifecycle/authorization/per-target state the owner's spec requires.
-- Idempotent: safe to re-run every backend start via repository.ensure_schema().

IF OBJECT_ID('dbo.stock_client_releases', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_client_releases (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_stock_client_releases PRIMARY KEY,
        version NVARCHAR(50) NOT NULL,
        release_id NVARCHAR(40) NOT NULL,
        build NVARCHAR(50) NULL,
        file_name NVARCHAR(260) NOT NULL,
        package_path NVARCHAR(500) NULL,
        sha256 CHAR(64) NOT NULL,
        file_size BIGINT NOT NULL,
        signature NVARCHAR(400) NULL,          -- base64 Ed25519 over the manifest
        release_notes NVARCHAR(1000) NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_scr_status DEFAULT ('DRAFT'),
        min_supported_version NVARCHAR(50) NULL,
        created_by NVARCHAR(100) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_scr_created_at DEFAULT SYSUTCDATETIME(),
        approved_by NVARCHAR(100) NULL,
        approved_at DATETIME2(0) NULL
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_releases') AND name = 'UX_stock_client_releases_version'
)
    CREATE UNIQUE INDEX UX_stock_client_releases_version ON dbo.stock_client_releases(version);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_releases') AND name = 'UX_stock_client_releases_release_id'
)
    CREATE UNIQUE INDEX UX_stock_client_releases_release_id ON dbo.stock_client_releases(release_id);


IF OBJECT_ID('dbo.stock_client_deployments', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_client_deployments (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_stock_client_deployments PRIMARY KEY,
        rollout_id NVARCHAR(40) NOT NULL,
        release_id UNIQUEIDENTIFIER NOT NULL,
        release_version NVARCHAR(50) NULL,
        scope NVARCHAR(20) NOT NULL,           -- ALL | SELECTED
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_scd_status DEFAULT ('DRAFT'),
                                               -- DRAFT|PENDING|IN_PROGRESS|COMPLETED|CANCELLED
        created_by NVARCHAR(100) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_scd_created_at DEFAULT SYSUTCDATETIME(),
        authorized_by NVARCHAR(100) NULL,
        authorized_at DATETIME2(0) NULL,
        completed_at DATETIME2(0) NULL,
        CONSTRAINT FK_scd_release FOREIGN KEY (release_id)
            REFERENCES dbo.stock_client_releases(id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_deployments') AND name = 'UX_stock_client_deployments_rollout_id'
)
    CREATE UNIQUE INDEX UX_stock_client_deployments_rollout_id ON dbo.stock_client_deployments(rollout_id);


IF OBJECT_ID('dbo.stock_client_deployment_targets', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_client_deployment_targets (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_stock_client_deployment_targets PRIMARY KEY,
        deployment_id UNIQUEIDENTIFIER NOT NULL,
        store_id UNIQUEIDENTIFIER NOT NULL,
        installation_id UNIQUEIDENTIFIER NULL,
        current_version NVARCHAR(50) NULL,
        target_version NVARCHAR(50) NOT NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_scdt_status DEFAULT ('PENDING'),
            -- PENDING|DOWNLOADING|VERIFYING|INSTALLING|RESTARTING|SUCCESS|FAILED|ROLLED_BACK|OFFLINE
        progress INT NOT NULL CONSTRAINT DF_scdt_progress DEFAULT (0),
        error NVARCHAR(1000) NULL,
        started_at DATETIME2(0) NULL,
        completed_at DATETIME2(0) NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_scdt_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_scdt_deployment FOREIGN KEY (deployment_id)
            REFERENCES dbo.stock_client_deployments(id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_deployment_targets') AND name = 'UX_scdt_deployment_store'
)
    CREATE UNIQUE INDEX UX_scdt_deployment_store
        ON dbo.stock_client_deployment_targets(deployment_id, store_id);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_deployment_targets') AND name = 'IX_scdt_store_status'
)
    CREATE INDEX IX_scdt_store_status
        ON dbo.stock_client_deployment_targets(store_id, status);


IF OBJECT_ID('dbo.stock_client_installations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_client_installations (
        installation_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_stock_client_installations PRIMARY KEY,
        tenant_id UNIQUEIDENTIFIER NULL,
        store_id UNIQUEIDENTIFIER NULL,
        device_id NVARCHAR(100) NULL,          -- modules.device_identity device id
        fingerprint_hash NVARCHAR(200) NULL,   -- derived hash only; never raw hw ids
        hostname NVARCHAR(200) NULL,
        local_ip NVARCHAR(60) NULL,
        observed_ip NVARCHAR(60) NULL,         -- server-seen request source IP
        os_version NVARCHAR(200) NULL,
        client_version NVARCHAR(50) NULL,
        watchdog_version NVARCHAR(50) NULL,
        client_status NVARCHAR(20) NULL,       -- RUNNING|STOPPED|UNKNOWN
        watchdog_status NVARCHAR(20) NULL,     -- RUNNING (reported by the service)
        last_update_status NVARCHAR(30) NULL,
        last_error NVARCHAR(1000) NULL,
        last_heartbeat_at DATETIME2(0) NULL,
        registered_at DATETIME2(0) NOT NULL CONSTRAINT DF_sci_registered_at DEFAULT SYSUTCDATETIME(),
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_sci_status DEFAULT ('ACTIVE')
            -- ACTIVE|DEVICE_CHANGED|REVOKED
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_installations') AND name = 'IX_sci_store'
)
    CREATE INDEX IX_sci_store ON dbo.stock_client_installations(store_id);


IF OBJECT_ID('dbo.stock_client_heartbeats', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_client_heartbeats (
        heartbeat_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_stock_client_heartbeats PRIMARY KEY,
        installation_id UNIQUEIDENTIFIER NOT NULL,
        client_version NVARCHAR(50) NULL,
        watchdog_version NVARCHAR(50) NULL,
        client_status NVARCHAR(20) NULL,
        watchdog_status NVARCHAR(20) NULL,
        last_update_status NVARCHAR(30) NULL,
        local_ip NVARCHAR(60) NULL,
        observed_ip NVARCHAR(60) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_sch_created_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_heartbeats') AND name = 'IX_sch_installation_created'
)
    CREATE INDEX IX_sch_installation_created
        ON dbo.stock_client_heartbeats(installation_id, created_at DESC);


IF OBJECT_ID('dbo.stock_client_events', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.stock_client_events (
        event_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_stock_client_events PRIMARY KEY,
        installation_id UNIQUEIDENTIFIER NULL,
        deployment_id UNIQUEIDENTIFIER NULL,
        store_id UNIQUEIDENTIFIER NULL,
        event_type NVARCHAR(50) NOT NULL,
        actor NVARCHAR(100) NULL,
        detail NVARCHAR(1000) NULL,
        target_version NVARCHAR(50) NULL,
        result NVARCHAR(30) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_sce_created_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.stock_client_events') AND name = 'IX_sce_created'
)
    CREATE INDEX IX_sce_created ON dbo.stock_client_events(created_at DESC);
