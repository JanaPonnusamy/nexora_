-- Remote Order Agent device registry (NEXORA_PLATFORM).
-- One row per enrolled agent device. Holds only the token HASH (never the token
-- or the derived secret). Lives beside dbo.nmv_enrollment_code so register +
-- code-claim touch one database.

IF OBJECT_ID('dbo.nmv_agent_device', 'U') IS NULL
CREATE TABLE dbo.nmv_agent_device (
    device_id      UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_nmv_agent_device PRIMARY KEY,
    store_id       UNIQUEIDENTIFIER NOT NULL,
    store_code     NVARCHAR(50) NOT NULL,
    token_hash     CHAR(64) NOT NULL,
    machine_name   NVARCHAR(200) NULL,
    agent_version  NVARCHAR(50) NULL,
    status         NVARCHAR(20) NOT NULL CONSTRAINT DF_nmv_agent_device_status DEFAULT 'active',
    created_at     DATETIME2 NOT NULL CONSTRAINT DF_nmv_agent_device_created DEFAULT SYSUTCDATETIME(),
    last_seen_at   DATETIME2 NULL,
    last_heartbeat NVARCHAR(MAX) NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_nmv_agent_device_token'
               AND object_id = OBJECT_ID('dbo.nmv_agent_device'))
CREATE UNIQUE INDEX UX_nmv_agent_device_token ON dbo.nmv_agent_device(token_hash);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_nmv_agent_device_store'
               AND object_id = OBJECT_ID('dbo.nmv_agent_device'))
CREATE INDEX IX_nmv_agent_device_store ON dbo.nmv_agent_device(store_id, status);
GO
