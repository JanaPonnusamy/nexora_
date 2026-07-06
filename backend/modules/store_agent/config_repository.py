from config.database import get_connection

def get_store_configuration(store_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT store_id,tenant_id,store_code,store_name,
            server_name,database_name,username,password_encrypted,
            connection_type,is_active
            FROM dbo.stores
            WHERE store_id=? AND is_active=1""",
            (store_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols,row))
    finally:
        conn.close()
