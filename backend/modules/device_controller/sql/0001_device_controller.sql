-- Nexora Device Controller: one SYSTEM service per PC that replaces the
-- per-app watchdogs (store agent / stock client) and lets HO start, stop,
-- pause, restart and update every Nexora app on that PC, edit the store
-- agent's HO links, and open audited remote PowerShell sessions.
--
-- Identity is the existing dbo.device_registrations row (app_type
-- 'device_controller'); device_id below is that id. Every message HO sends a
-- device (command / terminal open / terminal input / terminal close) is signed
-- with the HO command key and the signed payload is kept here, so the command
-- history doubles as the audit trail.
-- Idempotent: safe to re-run every backend start via repository.ensure_schema().

IF OBJECT_ID('dbo.dc_devices', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_devices (
        device_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_dc_devices PRIMARY KEY,
        hostname NVARCHAR(200) NULL,
        local_ip NVARCHAR(64) NULL,
        observed_ip NVARCHAR(64) NULL,
        os_version NVARCHAR(200) NULL,
        controller_version NVARCHAR(50) NULL,
        ho_url NVARCHAR(300) NULL,
        apps_json NVARCHAR(MAX) NULL,
        last_heartbeat_at DATETIME2(0) NULL,
        first_seen_at DATETIME2(0) NOT NULL CONSTRAINT DF_dc_devices_first DEFAULT SYSUTCDATETIME()
    );
END;

IF OBJECT_ID('dbo.dc_app_desired', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_app_desired (
        device_id UNIQUEIDENTIFIER NOT NULL,
        app_key NVARCHAR(40) NOT NULL,
        desired_state NVARCHAR(20) NOT NULL,      -- RUNNING | STOPPED | PAUSED
        paused_until DATETIME2(0) NULL,           -- PAUSED auto-resumes after this
        updated_by NVARCHAR(100) NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_dc_app_desired_upd DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_dc_app_desired PRIMARY KEY (device_id, app_key)
    );
END;

IF OBJECT_ID('dbo.dc_commands', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_commands (
        command_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_dc_commands PRIMARY KEY,
        device_id UNIQUEIDENTIFIER NOT NULL,
        app_key NVARCHAR(40) NOT NULL,
        action NVARCHAR(40) NOT NULL,
        args_json NVARCHAR(MAX) NULL,
        payload_json NVARCHAR(MAX) NOT NULL,      -- exactly what was signed
        signature NVARCHAR(200) NOT NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_dc_commands_status DEFAULT ('QUEUED'),
        -- QUEUED -> DELIVERED -> RUNNING -> SUCCEEDED | FAILED ; QUEUED -> CANCELLED | EXPIRED
        requested_by NVARCHAR(100) NULL,
        requested_at DATETIME2(0) NOT NULL CONSTRAINT DF_dc_commands_req DEFAULT SYSUTCDATETIME(),
        expires_at DATETIME2(0) NOT NULL,
        delivered_at DATETIME2(0) NULL,
        started_at DATETIME2(0) NULL,
        finished_at DATETIME2(0) NULL,
        exit_code INT NULL,
        result_text NVARCHAR(MAX) NULL
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dc_commands') AND name = 'IX_dc_commands_device_status')
    CREATE INDEX IX_dc_commands_device_status ON dbo.dc_commands(device_id, status, requested_at);

IF OBJECT_ID('dbo.dc_enroll_codes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_enroll_codes (
        code NVARCHAR(20) NOT NULL CONSTRAINT PK_dc_enroll_codes PRIMARY KEY,
        note NVARCHAR(200) NULL,
        created_by NVARCHAR(100) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_dc_enroll_created DEFAULT SYSUTCDATETIME(),
        expires_at DATETIME2(0) NOT NULL,
        max_uses INT NOT NULL CONSTRAINT DF_dc_enroll_max DEFAULT (1),
        use_count INT NOT NULL CONSTRAINT DF_dc_enroll_count DEFAULT (0),
        revoked BIT NOT NULL CONSTRAINT DF_dc_enroll_revoked DEFAULT (0)
    );
END;

IF OBJECT_ID('dbo.dc_terminal_sessions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_terminal_sessions (
        session_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_dc_terminal_sessions PRIMARY KEY,
        device_id UNIQUEIDENTIFIER NOT NULL,
        status NVARCHAR(20) NOT NULL,             -- OPENING | OPEN | CLOSING | CLOSED | FAILED
        open_payload_json NVARCHAR(MAX) NULL,
        open_signature NVARCHAR(200) NULL,
        open_delivered BIT NOT NULL CONSTRAINT DF_dc_term_open_del DEFAULT (0),
        close_payload_json NVARCHAR(MAX) NULL,
        close_signature NVARCHAR(200) NULL,
        close_delivered BIT NOT NULL CONSTRAINT DF_dc_term_close_del DEFAULT (0),
        opened_by NVARCHAR(100) NULL,
        opened_at DATETIME2(0) NOT NULL CONSTRAINT DF_dc_term_opened DEFAULT SYSUTCDATETIME(),
        closed_at DATETIME2(0) NULL,
        close_reason NVARCHAR(200) NULL
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dc_terminal_sessions') AND name = 'IX_dc_terminal_sessions_device')
    CREATE INDEX IX_dc_terminal_sessions_device ON dbo.dc_terminal_sessions(device_id, status);

IF OBJECT_ID('dbo.dc_terminal_io', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_terminal_io (
        seq BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_dc_terminal_io PRIMARY KEY,
        session_id UNIQUEIDENTIFIER NOT NULL,
        direction CHAR(3) NOT NULL,               -- IN (operator -> PC) | OUT (PC -> operator) | SYS
        data NVARCHAR(MAX) NOT NULL,
        payload_json NVARCHAR(MAX) NULL,          -- IN rows: the signed message
        signature NVARCHAR(200) NULL,
        delivered BIT NOT NULL CONSTRAINT DF_dc_term_io_del DEFAULT (0),
        actor NVARCHAR(100) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_dc_term_io_created DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dc_terminal_io') AND name = 'IX_dc_terminal_io_session')
    CREATE INDEX IX_dc_terminal_io_session ON dbo.dc_terminal_io(session_id, seq);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dc_terminal_io') AND name = 'IX_dc_terminal_io_pending')
    CREATE INDEX IX_dc_terminal_io_pending ON dbo.dc_terminal_io(direction, delivered, session_id);

-- Package catalog: every release file any HO node holds for a managed app,
-- with the node URL(s) it can be downloaded from. Nodes register what they
-- find in their local release folders (see packages.sync_local_packages), so
-- a release published on the build node is visible from every HO node.
IF OBJECT_ID('dbo.dc_packages', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.dc_packages (
        app_key NVARCHAR(40) NOT NULL,
        version NVARCHAR(50) NOT NULL,
        file_name NVARCHAR(260) NOT NULL,
        sha256 CHAR(64) NOT NULL,
        file_size BIGINT NOT NULL,
        signature NVARCHAR(400) NULL,             -- release-key Ed25519 over version|sha256|size
        source_urls NVARCHAR(1000) NULL,          -- comma list of HO base URLs that hold the file
        registered_at DATETIME2(0) NOT NULL CONSTRAINT DF_dc_packages_reg DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_dc_packages PRIMARY KEY (app_key, version)
    );
END;
