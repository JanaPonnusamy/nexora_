-- Forgot Password (NEXORA MEDIQ Phase 6F). Only a SHA-256 hash of the
-- reset token is stored -- the raw token exists only in the single email
-- sent to the user and is never written to this table, a log, or any
-- audit entry (see modules/password_reset/service.py). Each row is
-- single-use: used_at is set the moment the password is actually changed,
-- and any row for a user is superseded (not deleted -- kept for the audit
-- trail) the next time a reset is requested.
-- Documentation-only: repository.ensure_schema() creates this at runtime,
-- same pattern as modules/grid_settings/sql/0001_grid_settings.sql.
IF OBJECT_ID('dbo.password_reset_tokens', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.password_reset_tokens (
        token_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        user_id      UNIQUEIDENTIFIER NOT NULL,
        token_hash   CHAR(64)         NOT NULL,  -- sha256 hex digest of the raw token
        created_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
        expires_at   DATETIME2        NOT NULL,
        used_at      DATETIME2        NULL,
        request_ip   NVARCHAR(64)     NULL,
        CONSTRAINT PK_password_reset_tokens PRIMARY KEY (token_id)
    );
    CREATE INDEX IX_password_reset_tokens_token_hash ON dbo.password_reset_tokens(token_hash);
    CREATE INDEX IX_password_reset_tokens_user_id ON dbo.password_reset_tokens(user_id, created_at DESC);
END
