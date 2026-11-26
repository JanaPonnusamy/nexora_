"""Data access for Forgot Password (NEXORA MEDIQ Phase 6F).

Only a SHA-256 hash of the raw token is ever stored or read back here --
see sql/0001_password_reset_tokens.sql's header and service.py for why.
"""
from __future__ import annotations

from datetime import datetime, timezone

from config.database import get_connection

_SCHEMA_READY = False


def ensure_schema(cursor):
    """Idempotent -- safe to call before every query, same pattern as
    modules/grid_settings/repository.py."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    cursor.execute("""
        IF OBJECT_ID('dbo.password_reset_tokens', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.password_reset_tokens (
                token_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
                user_id      UNIQUEIDENTIFIER NOT NULL,
                token_hash   CHAR(64)         NOT NULL,
                created_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
                expires_at   DATETIME2        NOT NULL,
                used_at      DATETIME2        NULL,
                request_ip   NVARCHAR(64)     NULL,
                CONSTRAINT PK_password_reset_tokens PRIMARY KEY (token_id)
            );
            CREATE INDEX IX_password_reset_tokens_token_hash ON dbo.password_reset_tokens(token_hash);
            CREATE INDEX IX_password_reset_tokens_user_id ON dbo.password_reset_tokens(user_id, created_at DESC);
        END
    """)
    _SCHEMA_READY = True


def get_user_by_email(email: str):
    """Returns (user_id, username, email, is_active) or None. Case-
    insensitive match (SQL Server's default collation is already
    case-insensitive for NVARCHAR, but normalized here too so behavior
    doesn't silently depend on server collation)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, username, email, is_active FROM dbo.users WHERE LOWER(email) = LOWER(?)",
            email,
        )
        return cur.fetchone()
    finally:
        conn.close()


def count_recent_requests(user_id: str, since: datetime) -> int:
    """How many reset tokens (used or not) were created for this user since
    `since` -- backs the rate limit in service.py. Counting rows already
    written, not a separate in-memory counter, so the limit holds across
    process restarts and multiple backend workers."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dbo.password_reset_tokens WHERE user_id = ? AND created_at >= ?",
            user_id, since,
        )
        return int(cur.fetchone()[0] or 0)
    finally:
        conn.close()


def create_token(user_id: str, token_hash: str, expires_at: datetime, request_ip: str | None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        cur.execute(
            "INSERT INTO dbo.password_reset_tokens (user_id, token_hash, expires_at, request_ip) "
            "OUTPUT INSERTED.token_id VALUES (?, ?, ?, ?)",
            user_id, token_hash, expires_at, request_ip,
        )
        token_id = cur.fetchone()[0]
        conn.commit()
        return token_id
    finally:
        conn.close()


def get_valid_token(token_hash: str):
    """Returns (token_id, user_id, expires_at, used_at) for an unused,
    unexpired token matching this hash, or None. Expiry and single-use are
    both checked here, not left to the caller, so there is exactly one
    place that decides "is this token still good"."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        cur.execute(
            "SELECT token_id, user_id, expires_at, used_at FROM dbo.password_reset_tokens "
            "WHERE token_hash = ? AND used_at IS NULL AND expires_at > SYSUTCDATETIME()",
            token_hash,
        )
        return cur.fetchone()
    finally:
        conn.close()


def mark_used(token_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.password_reset_tokens SET used_at = SYSUTCDATETIME() WHERE token_id = ?",
            token_id,
        )
        conn.commit()
    finally:
        conn.close()


def invalidate_all_for_user(user_id: str):
    """Marks every still-valid outstanding token for this user as used,
    without ever having read back their raw values -- called right after a
    successful reset so an older, still-unexpired reset link (e.g. from an
    earlier request the user abandoned) can never be replayed afterward."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.password_reset_tokens SET used_at = SYSUTCDATETIME() "
            "WHERE user_id = ? AND used_at IS NULL",
            user_id,
        )
        conn.commit()
    finally:
        conn.close()


def update_password_hash(user_id: str, password_hash: str):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.users SET password_hash = ? WHERE user_id = ?",
            password_hash, user_id,
        )
        affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()
