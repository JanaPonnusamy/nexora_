IF OBJECT_ID('dbo.desktop_clients', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.desktop_clients (
        client_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_desktop_clients PRIMARY KEY,
        device_fingerprint NVARCHAR(200) NOT NULL,
        machine_name NVARCHAR(200) NULL,
        app_version NVARCHAR(50) NULL,
        status NVARCHAR(30) NOT NULL CONSTRAINT DF_desktop_clients_status DEFAULT ('pending'),
        tenant_id UNIQUEIDENTIFIER NULL,
        store_id UNIQUEIDENTIFIER NULL,
        store_code NVARCHAR(50) NULL,
        store_name NVARCHAR(200) NULL,
        server_base_url NVARCHAR(500) NULL,
        enabled BIT NOT NULL CONSTRAINT DF_desktop_clients_enabled DEFAULT (0),
        requested_store_name NVARCHAR(200) NULL,
        requested_store_code NVARCHAR(50) NULL,
        install_code NVARCHAR(100) NULL,
        last_seen_at DATETIME2(0) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_desktop_clients_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_desktop_clients_updated_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.desktop_clients')
      AND name = 'UX_desktop_clients_fingerprint'
)
BEGIN
    CREATE UNIQUE INDEX UX_desktop_clients_fingerprint
        ON dbo.desktop_clients(device_fingerprint);
END;

IF OBJECT_ID('dbo.desktop_client_config', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.desktop_client_config (
        config_id TINYINT NOT NULL CONSTRAINT PK_desktop_client_config PRIMARY KEY,
        latest_version NVARCHAR(50) NULL,
        min_version NVARCHAR(50) NULL,
        update_url NVARCHAR(500) NULL,
        force_update BIT NOT NULL CONSTRAINT DF_desktop_client_config_force_update DEFAULT (0),
        maintenance_message NVARCHAR(500) NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_desktop_client_config_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_desktop_client_config_singleton CHECK (config_id = 1)
    );
END;

IF NOT EXISTS (SELECT 1 FROM dbo.desktop_client_config WHERE config_id = 1)
BEGIN
    INSERT INTO dbo.desktop_client_config (config_id, force_update)
    VALUES (1, 0);
END;
