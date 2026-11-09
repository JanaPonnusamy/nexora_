
from config.database import get_connection

class TenantRepository:

    def ensure_schema(self):
        """dbo.tenants predates the per-tenant legacy Order DB name; add it
        once. Lets each tenant on a multi-tenant HO (.32: Success + SMS) point
        the Order Workspace / Legacy Order console at its own central database
        (e.g. OrderSMS) from the Tenants admin screen, instead of only via the
        LEGACY_DB_DATABASE_BY_TENANT env var (still read as a fallback -- see
        modules/legacy_order/database.py)."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            exists = cur.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = 'tenants' AND COLUMN_NAME = 'legacy_db_name'"
            ).fetchone()[0]
            if not exists:
                cur.execute("ALTER TABLE dbo.tenants ADD legacy_db_name NVARCHAR(200) NULL")
                conn.commit()
        finally:
            conn.close()

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active,legacy_db_name
        FROM dbo.tenants
        ORDER BY tenant_name
        """)
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_by_id(self, tenant_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active,legacy_db_name
        FROM dbo.tenants
        WHERE tenant_id = ?
        """, tenant_id)
        row = cur.fetchone()
        conn.close()
        return row

    def create(self, tenant_code, tenant_abbreviation, tenant_name, db_name, legacy_db_name=None):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO dbo.tenants (tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active,created_at,legacy_db_name)
        OUTPUT INSERTED.tenant_id
        VALUES (NEWID(), ?, ?, ?, ?, 1, GETDATE(), ?)
        """, tenant_code, tenant_abbreviation, tenant_name, db_name, legacy_db_name or None)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update(self, tenant_id, tenant_code, tenant_abbreviation, tenant_name, db_name, legacy_db_name=None):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.tenants
        SET tenant_code = ?, tenant_abbreviation = ?, tenant_name = ?, db_name = ?, legacy_db_name = ?
        WHERE tenant_id = ?
        """, tenant_code, tenant_abbreviation, tenant_name, db_name, legacy_db_name or None, tenant_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_active(self, tenant_id, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.tenants
        SET is_active = ?
        WHERE tenant_id = ?
        """, 1 if is_active else 0, tenant_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected
