
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

    def create(self, tenant_code, tenant_abbreviation, tenant_name, db_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO dbo.tenants (tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active)
        OUTPUT INSERTED.tenant_id
        VALUES (NEWID(), ?, ?, ?, ?, 1)
        """, tenant_code, tenant_abbreviation, tenant_name, db_name)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update(self, tenant_id, tenant_code, tenant_abbreviation, tenant_name, db_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.tenants
        SET tenant_code = ?, tenant_abbreviation = ?, tenant_name = ?, db_name = ?
        WHERE tenant_id = ?
        """, tenant_code, tenant_abbreviation, tenant_name, db_name, tenant_id)
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
