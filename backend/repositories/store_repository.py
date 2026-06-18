
from config.database import get_connection

class StoreRepository:

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active
        FROM dbo.stores
        ORDER BY store_code
        """)
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_by_id(self, store_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active
        FROM dbo.stores
        WHERE store_id = ?
        """, store_id)
        row = cur.fetchone()
        conn.close()
        return row

    def get_by_tenant(self, tenant_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active
        FROM dbo.stores
        WHERE tenant_id = ?
        ORDER BY store_code
        """, tenant_id)
        rows = cur.fetchall()
        conn.close()
        return rows
