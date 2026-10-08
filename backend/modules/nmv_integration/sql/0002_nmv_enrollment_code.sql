-- NMV device enrollment -- additive HO-side table.
--
-- This lives in NEXORA_PLATFORM (the platform DB), NOT OrderNMC, on purpose:
-- redeeming a code registers a device and assigns it a platform store, both of
-- which live here (dbo.device_registrations / dbo.device_store_assignments).
-- Co-locating the code table lets "claim the code" and "register the device"
-- touch one database, and keeps store identity (dbo.stores) a local join.
--
-- A one-time enrollment code lets an NMV device self-register WITHOUT a
-- store-user login: an HO super admin generates a code bound to a single store,
-- the device POSTs it once to /api/nmv-integration/v1/stores/{code}/enroll, and
-- the code is consumed. It reuses the existing Ed25519 device-identity
-- architecture (modules.device_identity) -- it is NOT a second auth mechanism;
-- it is only the first-contact bootstrap that the signed-token flow lacked.
--
-- Security: the plaintext code is NEVER stored or logged. Only its SHA-256 hash
-- is persisted (the code is 160-bit random, so a fast hash is safe: brute force
-- is infeasible by entropy, not by a slow KDF). The row records who created it,
-- when it expires, when it was used, and by which device -- auditable without
-- ever holding the secret.
--
-- Everything here is additive. No existing table is modified. Rollback = drop
-- this one table. Batches are separated by a line that begins with GO.

IF OBJECT_ID('dbo.nmv_enrollment_code', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.nmv_enrollment_code (
        id                  UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT PK_nmv_enrollment_code PRIMARY KEY,
        store_id            UNIQUEIDENTIFIER NOT NULL,   -- bound store (dbo.stores)
        store_code          NVARCHAR(40)  NOT NULL,      -- denormalised for audit/readability
        code_hash           CHAR(64)      NOT NULL,      -- SHA-256 hex of the normalised code
        status              NVARCHAR(20)  NOT NULL       -- active | used | superseded | locked
            CONSTRAINT DF_nmv_enroll_status DEFAULT ('active'),
        created_at          DATETIME2(0)  NOT NULL
            CONSTRAINT DF_nmv_enroll_created DEFAULT SYSUTCDATETIME(),
        expires_at          DATETIME2(0)  NOT NULL,
        used_at             DATETIME2(0)  NULL,
        device_id           UNIQUEIDENTIFIER NULL,       -- device that consumed it
        created_by          UNIQUEIDENTIFIER NULL,       -- admin who generated it
        created_by_username NVARCHAR(200) NULL,
        attempt_count       INT           NOT NULL
            CONSTRAINT DF_nmv_enroll_attempts DEFAULT (0)
    );
END;
GO

-- Codes are looked up by hash at redemption time; the hash is unique (160-bit
-- random source), so a direct unique-index lookup is both correct and O(1).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.nmv_enrollment_code')
      AND name = 'UX_nmv_enrollment_code_hash'
)
BEGIN
    CREATE UNIQUE INDEX UX_nmv_enrollment_code_hash
        ON dbo.nmv_enrollment_code(code_hash);
END;
GO

-- Supersede-active-on-generate and status filtering scan by (store_id, status).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.nmv_enrollment_code')
      AND name = 'IX_nmv_enrollment_code_store_status'
)
BEGIN
    CREATE INDEX IX_nmv_enrollment_code_store_status
        ON dbo.nmv_enrollment_code(store_id, status);
END;
GO
