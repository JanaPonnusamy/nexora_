from __future__ import annotations

"""Persistence for mobile refresh tokens.

Raw refresh tokens are never stored. Only a SHA-256 hash is written, so a
database disclosure does not hand an attacker usable credentials — the same
reason password_hash exists rather than a password column.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from config.database import get_connection

# Refresh tokens outlive the 12-hour access token by design: the point is that a
# field user is not thrown back to the login screen mid-task.
REFRESH_TOKEN_TTL_DAYS = 30

# 48 bytes of entropy, url-safe encoded.
_TOKEN_BYTES = 48


def ensure_schema() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF OBJECT_ID('dbo.mobile_refresh_tokens', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.mobile_refresh_tokens (
                    token_id UNIQUEIDENTIFIER NOT NULL
                        CONSTRAINT PK_mobile_refresh_tokens PRIMARY KEY,
                    user_id UNIQUEIDENTIFIER NOT NULL,
                    device_id NVARCHAR(200) NOT NULL,
                    token_hash CHAR(64) NOT NULL,
                    issued_at DATETIME2(0) NOT NULL
                        CONSTRAINT DF_mobile_refresh_tokens_issued DEFAULT SYSUTCDATETIME(),
                    expires_at DATETIME2(0) NOT NULL,
                    revoked_at DATETIME2(0) NULL,
                    revoked_reason NVARCHAR(100) NULL,
                    replaced_by UNIQUEIDENTIFIER NULL,
                    device_name NVARCHAR(200) NULL,
                    app_version NVARCHAR(50) NULL,
                    platform NVARCHAR(30) NULL,
                    ip NVARCHAR(64) NULL,
                    last_used_at DATETIME2(0) NULL
                );
            END;

            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.mobile_refresh_tokens')
                  AND name = 'UX_mobile_refresh_tokens_hash'
            )
            BEGIN
                CREATE UNIQUE INDEX UX_mobile_refresh_tokens_hash
                    ON dbo.mobile_refresh_tokens (token_hash);
            END;

            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.mobile_refresh_tokens')
                  AND name = 'IX_mobile_refresh_tokens_user_device'
            )
            BEGIN
                CREATE INDEX IX_mobile_refresh_tokens_user_device
                    ON dbo.mobile_refresh_tokens (user_id, device_id);
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def issue(
    user_id: str,
    device_id: str,
    device_name: Optional[str] = None,
    app_version: Optional[str] = None,
    platform: Optional[str] = None,
    ip: Optional[str] = None,
    replaces: Optional[str] = None,
) -> Dict[str, Any]:
    """Mints a refresh token and returns {token, token_id, expires_at}.

    The raw token is returned to the caller once and never persisted.
    """
    raw = generate_token()
    token_id = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.mobile_refresh_tokens
                (token_id, user_id, device_id, token_hash, expires_at,
                 device_name, app_version, platform, ip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            token_id,
            user_id,
            device_id,
            hash_token(raw),
            expires_at.replace(tzinfo=None),
            device_name,
            app_version,
            platform,
            ip,
        )
        if replaces:
            cur.execute(
                """
                UPDATE dbo.mobile_refresh_tokens
                   SET replaced_by = ?
                 WHERE token_id = ?
                """,
                token_id,
                replaces,
            )
        conn.commit()
    finally:
        conn.close()

    return {"token": raw, "token_id": token_id, "expires_at": expires_at}


def find(raw: str) -> Optional[Dict[str, Any]]:
    """Looks a token up by hash. Returns the row even when revoked/expired so
    the caller can distinguish 'unknown' from 'reused' — see service.refresh."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT token_id, user_id, device_id, expires_at, revoked_at
              FROM dbo.mobile_refresh_tokens
             WHERE token_hash = ?
            """,
            hash_token(raw),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return {
        "token_id": str(row[0]),
        "user_id": str(row[1]),
        "device_id": row[2],
        "expires_at": row[3],
        "revoked_at": row[4],
    }


def revoke(token_id: str, reason: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.mobile_refresh_tokens
               SET revoked_at = SYSUTCDATETIME(), revoked_reason = ?
             WHERE token_id = ? AND revoked_at IS NULL
            """,
            reason,
            token_id,
        )
        conn.commit()
    finally:
        conn.close()


def revoke_device(user_id: str, device_id: str, reason: str) -> int:
    """Revokes every live token for one device. Used on logout and, critically,
    on refresh-token reuse: a replayed token means the chain may be stolen, so
    the whole device family is burned rather than just the replayed link."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.mobile_refresh_tokens
               SET revoked_at = SYSUTCDATETIME(), revoked_reason = ?
             WHERE user_id = ? AND device_id = ? AND revoked_at IS NULL
            """,
            reason,
            user_id,
            device_id,
        )
        affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return affected if affected and affected > 0 else 0


def touch(token_id: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.mobile_refresh_tokens SET last_used_at = SYSUTCDATETIME() WHERE token_id = ?",
            token_id,
        )
        conn.commit()
    finally:
        conn.close()


def list_devices(user_id: str) -> List[Dict[str, Any]]:
    """Live sessions for a user, newest first — backs a 'signed-in devices' UI."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT device_id, device_name, platform, app_version,
                   issued_at, last_used_at, expires_at
              FROM dbo.mobile_refresh_tokens
             WHERE user_id = ?
               AND revoked_at IS NULL
               AND expires_at > SYSUTCDATETIME()
             ORDER BY issued_at DESC
            """,
            user_id,
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "device_id": r[0],
            "device_name": r[1],
            "platform": r[2],
            "app_version": r[3],
            "issued_at": r[4],
            "last_used_at": r[5],
            "expires_at": r[6],
        }
        for r in rows
    ]
