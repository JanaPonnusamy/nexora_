
from config.database import get_connection

class TenantRepository:

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active
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
        SELECT tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active
        FROM dbo.tenants
        WHERE tenant_id = ?
        """, tenant_id)
        row = cur.fetchone()
        conn.close()
        return row
