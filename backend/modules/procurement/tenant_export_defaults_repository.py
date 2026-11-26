"""Data access for the superadmin-owned desktop Procurement export defaults
(one row per tenant) — see sql/0032_tenant_export_defaults.sql.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def get(tenant_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_format, columns, updated_at, updated_by
            FROM procurement.tenant_export_defaults
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        )
        rows = _rows_to_dicts(cursor)
        return rows[0] if rows else None
    finally:
        conn.close()


def upsert(tenant_id, file_format, columns, updated_by):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.tenant_export_defaults
            SET file_format = ?, columns = ?, updated_at = GETDATE(), updated_by = ?
            WHERE tenant_id = ?
            """,
            (file_format, columns, updated_by, tenant_id),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO procurement.tenant_export_defaults
                    (tenant_id, file_format, columns, updated_by)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, file_format, columns, updated_by),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
