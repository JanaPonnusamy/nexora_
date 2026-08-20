"""Data access for generic per-user grid display settings (column order,
widths, padding) — one table, keyed by an arbitrary grid_key string, reused
by every grid in the app rather than one table per grid."""

from __future__ import annotations

from config.database import get_connection

_SCHEMA_READY = False


def ensure_schema(cursor):
    """Idempotent — safe to call before every query (nmw_sales_report style)."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    cursor.execute("""
        IF OBJECT_ID('dbo.user_grid_settings', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.user_grid_settings (
                user_id      UNIQUEIDENTIFIER NOT NULL,
                grid_key     NVARCHAR(100)    NOT NULL,
                tenant_id    UNIQUEIDENTIFIER NULL,
                settings     NVARCHAR(MAX)    NOT NULL,
                updated_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
                CONSTRAINT PK_user_grid_settings PRIMARY KEY (user_id, grid_key)
            );
        END
    """)
    _SCHEMA_READY = True


def get_settings(user_id: str, grid_key: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute(
            "SELECT settings, updated_at FROM dbo.user_grid_settings WHERE user_id = ? AND grid_key = ?",
            (user_id, grid_key),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {'settings': row[0], 'updated_at': row[1]}
    finally:
        conn.close()


def save_settings(user_id: str, tenant_id: str | None, grid_key: str, settings_json: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute(
            """
            MERGE dbo.user_grid_settings AS target
            USING (SELECT CAST(? AS UNIQUEIDENTIFIER) AS user_id, ? AS grid_key) AS source
            ON target.user_id = source.user_id AND target.grid_key = source.grid_key
            WHEN MATCHED THEN
                UPDATE SET settings = ?, tenant_id = ?, updated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (user_id, grid_key, tenant_id, settings)
                VALUES (source.user_id, source.grid_key, ?, ?);
            """,
            (user_id, grid_key, settings_json, tenant_id, tenant_id, settings_json),
        )
        conn.commit()
    finally:
        conn.close()


def reset_settings(user_id: str, grid_key: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute(
            "DELETE FROM dbo.user_grid_settings WHERE user_id = ? AND grid_key = ?",
            (user_id, grid_key),
        )
        conn.commit()
    finally:
        conn.close()
