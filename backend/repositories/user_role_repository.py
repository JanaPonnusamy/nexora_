
import os
import uuid
import bcrypt

from config.database import get_connection

# One seed login per role so every access level can be tested/used
# immediately after a fresh install. Passwords are intentionally simple
# defaults - rotate them for any real deployment.
_SETUP_PASSWORD = os.getenv("UNINEX_SETUP_PASSWORD", "").strip()

_SEED_USERS = [
    ('superadmin', 'Nexora@123', 'Super', 'Admin', 'SUPER_ADMIN', True),
    ('platformowner', 'Nexora@123', 'Platform', 'Owner', 'PLATFORM_OWNER', True),
    ('tenantadmin', 'Nexora@123', 'Tenant', 'Admin', 'TENANT_ADMIN', False),
    ('storeadmin', 'Nexora@123', 'Store', 'Admin', 'STORE_ADMIN', False),
    ('storemanager', 'Nexora@123', 'Store', 'Manager', 'STORE_MANAGER', False),
    ('storeuser', 'Nexora@123', 'Store', 'User', 'STORE_USER', False),
    ('syncoperator', 'Nexora@123', 'Sync', 'Operator', 'SYNC_OPERATOR', False),
]
if _SETUP_PASSWORD:
    _SEED_USERS.append(('setupdeploy', _SETUP_PASSWORD, 'Setup', 'Deploy', 'PLATFORM_OWNER', True))

class UserRoleRepository:

    def seed_all_role_users(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT TOP 1 store_id FROM dbo.stores ORDER BY store_code")
        store = cur.fetchone()
        if not store:
            conn.close()
            return 0
        store_id = str(store[0])

        created = 0
        for username, password, first_name, last_name, role_name, is_platform_user in _SEED_USERS:
            cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", role_name)
            role_row = cur.fetchone()
            if not role_row:
                continue
            role_id = str(role_row[0])

            cur.execute("SELECT user_id FROM dbo.users WHERE username=?", username)
            existing = cur.fetchone()

            if existing:
                user_id = str(existing[0])
            else:
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                user_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO dbo.users (user_id,username,password_hash,first_name,last_name,is_platform_user,is_active,created_at) "
                    "VALUES (?,?,?,?,?,?,1,GETDATE())",
                    user_id, username, password_hash, first_name, last_name, 1 if is_platform_user else 0
                )
                created += 1

            cur.execute(
                "SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?",
                user_id, store_id, role_id
            )
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)",
                    user_id, store_id, role_id
                )

        conn.commit()
        conn.close()
        return created

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

    def seed_default_role_for_all_users(self, default_role_name='STORE_USER'):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", default_role_name)
        role_row = cur.fetchone()
        if not role_row:
            conn.close()
            return 0
        role_id = str(role_row[0])

        cur.execute("""
        SELECT u.user_id, u.tenant_id
        FROM dbo.users u
        WHERE NOT EXISTS (SELECT 1 FROM dbo.user_store_roles usr WHERE usr.user_id = u.user_id)
        """)
        users = cur.fetchall()

        assigned = 0
        for user_id, tenant_id in users:
            cur.execute("SELECT TOP 1 store_id FROM dbo.stores WHERE tenant_id=? ORDER BY store_code", tenant_id)
            store = cur.fetchone()
            if not store:
                continue
            store_id = str(store[0])
            cur.execute(
                "INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)",
                str(user_id), store_id, role_id
            )
            assigned += 1

        conn.commit()
        conn.close()
        return assigned

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
