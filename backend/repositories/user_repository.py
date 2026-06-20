
from config.database import get_connection

# Column order returned by the list query (see get_all).
LIST_COLUMNS = """
        u.user_id,
        u.username,
        LTRIM(RTRIM(u.first_name + ISNULL(' ' + u.last_name, ''))) AS full_name,
        u.tenant_id,
        t.tenant_name,
        u.is_active,
        u.last_login,
        (SELECT COUNT(DISTINCT usr.store_id) FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id) AS store_count,
        (SELECT COUNT(DISTINCT usr.role_id) FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id) AS role_count
"""

class UserRepository:

    # ----- existing authentication helpers -----

    def get_user_by_username(self, username):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT user_id,username,password_hash,first_name,is_platform_user,is_active
        FROM dbo.users
        WHERE username = ?
        """, username)
        row = cur.fetchone()
        conn.close()
        return row

    def update_last_login(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.users
        SET last_login = GETDATE()
        WHERE user_id = ?
        """, user_id)
        conn.commit()
        conn.close()

    # ----- user management (CRUD) -----

    def get_all(self, search=None, tenant_id=None, store_id=None, role_id=None, status=None):
        conn = get_connection()
        cur = conn.cursor()

        where = []
        params = []

        if search:
            where.append("(u.username LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ? OR u.email LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like, like])
        if tenant_id:
            where.append("u.tenant_id = ?")
            params.append(tenant_id)
        if store_id:
            where.append("EXISTS (SELECT 1 FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id AND usr.store_id = ?)")
            params.append(store_id)
        if role_id:
            where.append("EXISTS (SELECT 1 FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id AND usr.role_id = ?)")
            params.append(role_id)
        if status == 'active':
            where.append("u.is_active = 1")
        elif status == 'inactive':
            where.append("u.is_active = 0")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        cur.execute(f"""
        SELECT
        {LIST_COLUMNS}
        FROM dbo.users u
        LEFT JOIN dbo.tenants t ON u.tenant_id = t.tenant_id
        {where_sql}
        ORDER BY u.first_name, u.last_name
        """, params)

        rows = cur.fetchall()
        conn.close()
        return rows

    def get_by_id(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT
            u.user_id,
            u.username,
            LTRIM(RTRIM(u.first_name + ISNULL(' ' + u.last_name, ''))) AS full_name,
            u.first_name,
            u.last_name,
            u.email,
            u.mobile,
            u.tenant_id,
            t.tenant_name,
            u.is_platform_user,
            u.is_active,
            u.last_login,
            (SELECT COUNT(DISTINCT usr.store_id) FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id) AS store_count,
            (SELECT COUNT(DISTINCT usr.role_id) FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id) AS role_count
        FROM dbo.users u
        LEFT JOIN dbo.tenants t ON u.tenant_id = t.tenant_id
        WHERE u.user_id = ?
        """, user_id)
        row = cur.fetchone()
        conn.close()
        return row

    def username_exists(self, username, exclude_id=None):
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute("SELECT COUNT(*) FROM dbo.users WHERE username = ? AND user_id <> ?", username, exclude_id)
        else:
            cur.execute("SELECT COUNT(*) FROM dbo.users WHERE username = ?", username)
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def create(self, username, first_name, last_name, password_hash):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO dbo.users (user_id, username, password_hash, first_name, last_name, is_platform_user, is_active, created_at)
        OUTPUT INSERTED.user_id
        VALUES (NEWID(), ?, ?, ?, ?, 0, 1, GETDATE())
        """, username, password_hash, first_name, last_name)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update(self, user_id, username, first_name, last_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.users
        SET username = ?, first_name = ?, last_name = ?, updated_at = GETDATE()
        WHERE user_id = ?
        """, username, first_name, last_name, user_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_active(self, user_id, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.users
        SET is_active = ?, updated_at = GETDATE()
        WHERE user_id = ?
        """, 1 if is_active else 0, user_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected
