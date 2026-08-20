
from config.database import get_connection

class StoreRepository:

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active,
               is_warehouse,store_order
        FROM dbo.stores
        ORDER BY store_order,store_code
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
    
    def get_agent_config(self, store_id):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT
            store_id,
            store_code,
            server_name,
            database_name,
            username,
            password_encrypted,
            connection_type,
            agent_version,
            is_active
        FROM dbo.stores
        WHERE store_id = ?
        """, store_id)

        row = cur.fetchone()

        conn.close()

        return row

    def store_code_exists(self, store_code, tenant_id, exclude_id=None):
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute(
                "SELECT COUNT(*) FROM dbo.stores WHERE store_code = ? AND tenant_id = ? AND store_id <> ?",
                store_code, tenant_id, exclude_id
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM dbo.stores WHERE store_code = ? AND tenant_id = ?",
                store_code, tenant_id
            )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def create(self, tenant_id, store_code, store_name, server_name, database_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO dbo.stores (store_id, tenant_id, store_code, store_name, server_name, database_name, is_active, created_at)
        OUTPUT INSERTED.store_id
        VALUES (NEWID(), ?, ?, ?, ?, ?, 1, GETDATE())
        """, tenant_id, store_code, store_name, server_name, database_name)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update(self, store_id, tenant_id, store_code, store_name, server_name, database_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.stores
        SET tenant_id = ?, store_code = ?, store_name = ?, server_name = ?, database_name = ?, updated_at = GETDATE()
        WHERE store_id = ?
        """, tenant_id, store_code, store_name, server_name, database_name, store_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_active(self, store_id, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.stores
        SET is_active = ?, updated_at = GETDATE()
        WHERE store_id = ?
        """, 1 if is_active else 0, store_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected