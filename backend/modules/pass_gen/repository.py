"""Data access for Pass Gen — the store → numeric-passcode-code mapping."""

from config.database import get_connection


def list_stores(tenant_id=None):
    """Active stores with their numeric passcode code (None when unmapped)."""
    sql = """
        SELECT s.store_id, s.tenant_id, s.store_code, s.store_name, m.numeric_code
        FROM dbo.stores s
        LEFT JOIN dbo.pass_gen_store_code m ON m.store_id = s.store_id
        WHERE s.is_active = 1
          AND (? IS NULL OR s.tenant_id = ?)
        ORDER BY s.store_order, s.store_code
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (tenant_id, tenant_id))
        return [
            {
                'store_id': str(row[0]),
                'tenant_id': str(row[1]),
                'store_code': row[2],
                'store_name': row[3],
                'numeric_code': row[4],
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def set_numeric_code(store_id, numeric_code):
    """Upsert (or clear, when numeric_code is None) a store's numeric code."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if numeric_code is None:
            cursor.execute(
                "DELETE FROM dbo.pass_gen_store_code WHERE store_id = ?",
                (store_id,),
            )
        else:
            cursor.execute(
                """
                MERGE dbo.pass_gen_store_code AS target
                USING (SELECT CAST(? AS UNIQUEIDENTIFIER) AS store_id, ? AS numeric_code) AS source
                ON target.store_id = source.store_id
                WHEN MATCHED THEN
                    UPDATE SET numeric_code = source.numeric_code, updated_at = SYSUTCDATETIME()
                WHEN NOT MATCHED THEN
                    INSERT (store_id, numeric_code) VALUES (source.store_id, source.numeric_code);
                """,
                (store_id, numeric_code),
            )
        conn.commit()
    finally:
        conn.close()
