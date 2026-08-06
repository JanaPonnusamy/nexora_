-- Remote control + self-update for store agents (watchdog service).
--
-- store_agent_registry gains a desired vs actual split: connection_status /
-- agent_version are what the agent LAST reported; desired_state /
-- desired_version are what HO wants it to be. The watchdog polls
-- /agent/watchdog/state and reconciles the two, so "stop store X" or
-- "push version Y" from HO becomes a real action on that machine within one
-- watchdog cycle instead of a database flag nobody enforces.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.store_agent_registry')
      AND name = 'desired_state'
)
BEGIN
    ALTER TABLE dbo.store_agent_registry
        ADD desired_state NVARCHAR(20) NOT NULL
            CONSTRAINT DF_store_agent_registry_desired_state DEFAULT ('RUNNING');
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.store_agent_registry')
      AND name = 'desired_version'
)
BEGIN
    ALTER TABLE dbo.store_agent_registry
        ADD desired_version NVARCHAR(50) NULL;
END;

IF OBJECT_ID('dbo.agent_releases', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.agent_releases (
        version NVARCHAR(50) NOT NULL CONSTRAINT PK_agent_releases PRIMARY KEY,
        file_name NVARCHAR(260) NOT NULL,
        sha256 CHAR(64) NOT NULL,
        file_size BIGINT NOT NULL,
        is_current BIT NOT NULL CONSTRAINT DF_agent_releases_is_current DEFAULT (0),
        notes NVARCHAR(500) NULL,
        released_at DATETIME2(0) NOT NULL CONSTRAINT DF_agent_releases_released_at DEFAULT SYSUTCDATETIME()
    );
END;

-- At most one current release at a time (the watchdog always asks for "current").
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.agent_releases')
      AND name = 'UX_agent_releases_is_current'
)
BEGIN
    CREATE UNIQUE INDEX UX_agent_releases_is_current
        ON dbo.agent_releases(is_current)
        WHERE is_current = 1;
END;

IF OBJECT_ID('dbo.agent_watchdog_status', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.agent_watchdog_status (
        store_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_agent_watchdog_status PRIMARY KEY,
        watchdog_version NVARCHAR(50) NULL,
        installed_agent_version NVARCHAR(50) NULL,
        service_state NVARCHAR(20) NULL,
        last_action NVARCHAR(300) NULL,
        last_heartbeat DATETIME2(0) NULL
    );
END;

IF OBJECT_ID('dbo.agent_watchdog_audit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.agent_watchdog_audit (
        audit_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_agent_watchdog_audit PRIMARY KEY,
        store_id UNIQUEIDENTIFIER NOT NULL,
        event_type NVARCHAR(50) NOT NULL,
        detail NVARCHAR(400) NULL,
        target_version NVARCHAR(50) NULL,
        created_at DATETIME2(0) NOT NULL
            CONSTRAINT DF_agent_watchdog_audit_created_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.agent_watchdog_audit')
      AND name = 'IX_agent_watchdog_audit_store_created'
)
BEGIN
    CREATE INDEX IX_agent_watchdog_audit_store_created
        ON dbo.agent_watchdog_audit(store_id, created_at DESC);
END;
