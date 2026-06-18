
from config.database import get_connection

class UserRoleRepository:

    def seed_superadmin_assignment(self):
        user_id = '4055B2C9-30E8-4062-9D52-666EF0769D4B'
        role_id = '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7'

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT TOP 1 store_id FROM dbo.stores ORDER BY store_code")
        store = cur.fetchone()

        if not store:
            conn.close()
            return 0

        store_id = str(store[0])

        cur.execute("SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?", user_id, store_id, role_id)

        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)", user_id, store_id, role_id)
            conn.commit()
            conn.close()
            return 1

        conn.close()
        return 0

    def get_user_roles(self, user_id):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT r.role_id,r.role_name,s.store_id,s.store_code,s.store_name
        FROM dbo.user_store_roles usr
        INNER JOIN dbo.roles r ON usr.role_id=r.role_id
        INNER JOIN dbo.stores s ON usr.store_id=s.store_id
        WHERE usr.user_id=?
        """, user_id)

        rows = cur.fetchall()
        conn.close()
        return rows
