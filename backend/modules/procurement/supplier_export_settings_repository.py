"""Data access for per-supplier Export Settings memory (Export Monitor
overhaul) — see sql/0018_supplier_export_settings.sql for why this is its
own table rather than columns on sync.Suppliers.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def get(tenant_id, store_id, supplier_code):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT format, columns, order_qty_header, sort_by, export_folder_path
            FROM procurement.supplier_export_settings
            WHERE tenant_id = ? AND store_id = ? AND supplier_code = ?
            """,
            (tenant_id, store_id, supplier_code),
        )
        rows = _rows_to_dicts(cursor)
        return rows[0] if rows else None
    finally:
        conn.close()


def upsert(tenant_id, store_id, supplier_code, format, columns, order_qty_header, sort_by, export_folder_path):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.supplier_export_settings
            SET format = ?, columns = ?, order_qty_header = ?, sort_by = ?,
                export_folder_path = ?, updated_at = GETDATE()
            WHERE tenant_id = ? AND store_id = ? AND supplier_code = ?
            """,
            (format, columns, order_qty_header, sort_by, export_folder_path,
             tenant_id, store_id, supplier_code),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO procurement.supplier_export_settings
                    (tenant_id, store_id, supplier_code, format, columns,
                     order_qty_header, sort_by, export_folder_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, store_id, supplier_code, format, columns,
                 order_qty_header, sort_by, export_folder_path),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
