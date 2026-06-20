
from config.database import get_connection
import uuid

class RoleRepository:

    def seed_roles(self):
        roles = [
            ('SUPER_ADMIN','Platform Control'),
            ('TENANT_ADMIN','Tenant Control'),
            ('STORE_ADMIN','Store Administration'),
            ('STORE_MANAGER','Store Operations'),
            ('STORE_USER','Standard User'),
            ('SYNC_OPERATOR','Sync Monitoring')
        ]

        conn = get_connection()
        cur = conn.cursor()
        inserted = 0

        for role_name, description in roles:
            cur.execute("SELECT COUNT(*) FROM dbo.roles WHERE role_name=?", role_name)

            if cur.fetchone()[0] > 0:
                continue

            cur.execute(
                "INSERT INTO dbo.roles(role_id,role_name,description,is_active) VALUES (?,?,?,1)",
                str(uuid.uuid4()),
                role_name,
                description
            )

            inserted += 1

        conn.commit()
        conn.close()

        return inserted

    def get_all_roles(self, search=None, status=None):
        conn = get_connection()
        cur = conn.cursor()

        where = []
        params = []

        if search:
            where.append("(r.role_name LIKE ? OR r.description LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        if status == 'active':
            where.append("r.is_active = 1")
        elif status == 'inactive':
            where.append("r.is_active = 0")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        cur.execute(f"""
        SELECT
            r.role_id,
            r.role_name,
            r.description,
            r.is_active,
            (SELECT COUNT(DISTINCT usr.user_id) FROM dbo.user_store_roles usr WHERE usr.role_id = r.role_id) AS assigned_users
        FROM dbo.roles r
        {where_sql}
        ORDER BY r.role_name
        """, params)

        rows = cur.fetchall()
        conn.close()
        return rows

    def get_role_by_id(self, role_id):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT
            r.role_id,
            r.role_name,
            r.description,
            r.is_active,
            (SELECT COUNT(DISTINCT usr.user_id) FROM dbo.user_store_roles usr WHERE usr.role_id = r.role_id) AS assigned_users
        FROM dbo.roles r
        WHERE r.role_id = ?
        """, role_id)

        row = cur.fetchone()
        conn.close()
        return row

    def role_name_exists(self, role_name, exclude_id=None):
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute("SELECT COUNT(*) FROM dbo.roles WHERE role_name = ? AND role_id <> ?", role_name, exclude_id)
        else:
            cur.execute("SELECT COUNT(*) FROM dbo.roles WHERE role_name = ?", role_name)
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def create(self, role_name, description):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO dbo.roles (role_id, role_name, description, is_active)
        OUTPUT INSERTED.role_id
        VALUES (NEWID(), ?, ?, 1)
        """, role_name, description)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update(self, role_id, role_name, description):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.roles
        SET role_name = ?, description = ?
        WHERE role_id = ?
        """, role_name, description, role_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_active(self, role_id, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.roles
        SET is_active = ?
        WHERE role_id = ?
        """, 1 if is_active else 0, role_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected
