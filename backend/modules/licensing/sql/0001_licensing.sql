-- License Activation module: trial -> licensed state machine per tenant,
-- plus a single-row-per-store usage/last-active table.
--
-- tenant_licenses is the state machine (trial_active/trial_expired/licensed/
-- revoked). tenant_license_audit is an append-only event log for admin
-- visibility ONLY - it is intentionally the one append-log table here.
-- tenant_usage_status is the opposite: exactly one row per store_id,
-- UPDATEd in place on every store-agent check-in, never inserted a second
-- time for the same store (see repository.record_checkin).

IF OBJECT_ID('dbo.tenant_licenses', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.tenant_licenses (
        tenant_id        UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_tenant_licenses PRIMARY KEY,
        license_state    NVARCHAR(20) NOT NULL
            CONSTRAINT DF_tenant_licenses_state DEFAULT ('trial_active'),
        trial_days       INT NOT NULL CONSTRAINT DF_tenant_licenses_trial_days DEFAULT (14),
        trial_started_at DATETIME2(0) NOT NULL
            CONSTRAINT DF_tenant_licenses_trial_started DEFAULT SYSUTCDATETIME(),
        trial_ends_at    DATETIME2(0) NOT NULL,
        license_key      NVARCHAR(100) NULL,
        issued_at        DATETIME2(0) NULL,
        issued_by        NVARCHAR(200) NULL,
        expires_at       DATETIME2(0) NULL,
        revoked_at       DATETIME2(0) NULL,
        revoked_by       NVARCHAR(200) NULL,
        notes            NVARCHAR(500) NULL,
        created_at       DATETIME2(0) NOT NULL CONSTRAINT DF_tenant_licenses_created_at DEFAULT SYSUTCDATETIME(),
        updated_at       DATETIME2(0) NOT NULL CONSTRAINT DF_tenant_licenses_updated_at DEFAULT SYSUTCDATETIME()
    );
END;

IF OBJECT_ID('dbo.tenant_license_audit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.tenant_license_audit (
        audit_id    BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_tenant_license_audit PRIMARY KEY,
        tenant_id   UNIQUEIDENTIFIER NOT NULL,
        event_type  NVARCHAR(30) NOT NULL, -- trial_started | issued | revoked | renewed
        detail      NVARCHAR(400) NULL,
        actor       NVARCHAR(200) NULL,
        created_at  DATETIME2(0) NOT NULL
            CONSTRAINT DF_tenant_license_audit_created_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.tenant_license_audit')
      AND name = 'IX_tenant_license_audit_tenant_created'
)
BEGIN
    CREATE INDEX IX_tenant_license_audit_tenant_created
        ON dbo.tenant_license_audit(tenant_id, created_at DESC);
END;

-- Single row per store: last-active date/time only, upserted every check-in.
IF OBJECT_ID('dbo.tenant_usage_status', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.tenant_usage_status (
        store_id          UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_tenant_usage_status PRIMARY KEY,
        tenant_id         UNIQUEIDENTIFIER NOT NULL,
        last_active_date  DATE NOT NULL,
        last_active_time  TIME(0) NOT NULL,
        last_active_at    DATETIME2(0) NOT NULL,
        agent_version     NVARCHAR(50) NULL,
        updated_at        DATETIME2(0) NOT NULL
            CONSTRAINT DF_tenant_usage_status_updated_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.tenant_usage_status')
      AND name = 'IX_tenant_usage_status_tenant'
)
BEGIN
    CREATE INDEX IX_tenant_usage_status_tenant ON dbo.tenant_usage_status(tenant_id);
END;

-- Backfill: every tenant that existed before this module shipped is already
-- a paying/live tenant, not a fresh demo install - mark them licensed so
-- nobody already live gets retroactively trial-gated.
INSERT INTO dbo.tenant_licenses
    (tenant_id, license_state, trial_days, trial_started_at, trial_ends_at,
     issued_at, issued_by, notes)
SELECT
    t.tenant_id, 'licensed', 0, t.created_at, t.created_at,
    SYSUTCDATETIME(), 'MIGRATION_BACKFILL', 'Backfilled as licensed on licensing module rollout'
FROM dbo.tenants t
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.tenant_licenses tl WHERE tl.tenant_id = t.tenant_id
);
