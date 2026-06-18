
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

    def get_all_roles(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT role_id, role_name, description, is_active FROM dbo.roles ORDER BY role_name")

        rows = cur.fetchall()
        conn.close()
        return rows

    def get_role_by_id(self, role_id):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT role_id, role_name, description, is_active FROM dbo.roles WHERE role_id=?",
            role_id
        )

        row = cur.fetchone()
        conn.close()
        return row
