
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
        SELECT user_id,username,password_hash,first_name,is_platform_user,is_active,tenant_id
        FROM dbo.users
        WHERE username = ?
        """, username)
        row = cur.fetchone()
        conn.close()
        return row

    def get_user_core_by_id(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT user_id,username,password_hash,first_name,is_platform_user,is_active,tenant_id
        FROM dbo.users
        WHERE user_id = ?
        """, user_id)
        row = cur.fetchone()
        conn.close()
        return row

    def get_user_modules(self, user_id):
        conn = get_connection()
        cur = conn.cursor()

        # SUPER_ADMIN / PLATFORM_OWNER bypass role_module_access entirely and
        # get every active module with full rights, including modules added
        # later that have no seeded permission rows yet.
        cur.execute("""
        SELECT COUNT(*)
        FROM dbo.user_store_roles usr
        INNER JOIN dbo.roles r ON r.role_id = usr.role_id
        WHERE usr.user_id = ?
          AND usr.is_active = 1
          AND r.role_name IN ('SUPER_ADMIN','PLATFORM_OWNER')
        """, user_id)
        is_full_access = cur.fetchone()[0] > 0

        if is_full_access:
            cur.execute("""
            SELECT module_code, module_name, 1, 1, 1, 1, 1
            FROM dbo.modules
            WHERE is_active = 1
            ORDER BY module_name
            """)
            rows = cur.fetchall()
            conn.close()
            return rows

        cur.execute("""
        SELECT DISTINCT
            m.module_code,
            m.module_name,
            ISNULL(rma.can_view, 0) AS can_view,
            ISNULL(rma.can_create, 0) AS can_create,
            ISNULL(rma.can_edit, 0) AS can_edit,
            ISNULL(rma.can_delete, 0) AS can_delete,
            ISNULL(rma.can_export, 0) AS can_export
        FROM dbo.user_store_roles usr
        INNER JOIN dbo.role_module_access rma
            ON rma.role_id = usr.role_id
           AND ISNULL(rma.is_active, 1) = 1
        INNER JOIN dbo.modules m
            ON m.module_id = rma.module_id
           AND m.is_active = 1
        WHERE usr.user_id = ?
          AND usr.is_active = 1
          AND ISNULL(rma.can_view, 0) = 1
        ORDER BY m.module_name
        """, user_id)
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_user_roles(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT DISTINCT
            r.role_id,
            r.role_name,
            s.store_id,
            s.store_code,
            s.store_name
        FROM dbo.user_store_roles usr
        INNER JOIN dbo.roles r ON r.role_id = usr.role_id
        INNER JOIN dbo.stores s ON s.store_id = usr.store_id
        WHERE usr.user_id = ?
          AND usr.is_active = 1
        ORDER BY r.role_name, s.store_code
        """, user_id)
        rows = cur.fetchall()
        conn.close()
        return rows

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

    # ----- single active session (one login per user at a time) -----

    def is_session_active(self, user_id, lease_minutes):
        """True when the user has a session whose last activity is within the
        lease window - i.e. someone is currently signed in. A crashed/closed
        client stops heart-beating, so its session goes stale after the lease
        and no longer blocks a fresh login."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT CASE WHEN active_session_id IS NOT NULL
                     AND active_session_at IS NOT NULL
                     AND active_session_at >= DATEADD(MINUTE, -?, GETDATE())
               THEN 1 ELSE 0 END
        FROM dbo.users WHERE user_id = ?
        """, lease_minutes, user_id)
        row = cur.fetchone()
        conn.close()
        return bool(row and row[0])

    def get_active_session_id(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT active_session_id FROM dbo.users WHERE user_id = ?", user_id)
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    def set_active_session(self, user_id, session_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.users SET active_session_id = ?, active_session_at = GETDATE() WHERE user_id = ?",
            session_id, user_id,
        )
        conn.commit()
        conn.close()

    def touch_active_session(self, user_id, session_id):
        """Heart-beat: refresh last-activity so the lease stays alive while the
        client keeps making requests. Guarded on session_id so a superseded
        token can't keep a session it no longer owns alive."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.users SET active_session_at = GETDATE() "
            "WHERE user_id = ? AND active_session_id = ?",
            user_id, session_id,
        )
        conn.commit()
        conn.close()

    def clear_active_session(self, user_id, session_id=None):
        """Release the session on explicit sign-out. Only clears when the caller
        owns the current session (session_id match) unless session_id is None."""
        conn = get_connection()
        cur = conn.cursor()
        if session_id:
            cur.execute(
                "UPDATE dbo.users SET active_session_id = NULL, active_session_at = NULL "
                "WHERE user_id = ? AND active_session_id = ?",
                user_id, session_id,
            )
        else:
            cur.execute(
                "UPDATE dbo.users SET active_session_id = NULL, active_session_at = NULL WHERE user_id = ?",
                user_id,
            )
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
