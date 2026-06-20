from config.database import get_connection

class RoleModuleAccessRepository:

    def seed_super_admin_permissions(self):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("EXEC dbo.sp_RoleModuleAccess_Seed")

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Super Admin permissions seeded successfully"
        }

    def get_role_permission_matrix(self, role_id):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT r.role_id,r.role_name,m.module_id,m.module_code,m.module_name,rma.can_view,rma.can_create,rma.can_edit,rma.can_delete,rma.can_export FROM dbo.role_module_access rma INNER JOIN dbo.roles r ON rma.role_id=r.role_id INNER JOIN dbo.modules m ON rma.module_id=m.module_id WHERE rma.role_id=? ORDER BY m.module_name",
            role_id
        )

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        modules = []

        for row in rows:
            modules.append({
                "module_id": str(row[2]),
                "module_code": row[3],
                "module_name": row[4],
                "can_view": bool(row[5]),
                "can_create": bool(row[6]),
                "can_edit": bool(row[7]),
                "can_delete": bool(row[8]),
                "can_export": bool(row[9])
            })

        return {
            "role_id": str(rows[0][0]),
            "role_name": rows[0][1],
            "total_modules": len(modules),
            "modules": modules
        }

    # ----- permission matrix (role <-> module assignment) -----

    def get_matrix(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT role_id, role_name FROM dbo.roles WHERE is_active = 1 ORDER BY role_name")
        roles = [{"role_id": str(r[0]), "role_name": r[1]} for r in cur.fetchall()]

        cur.execute("SELECT module_id, module_code, module_name FROM dbo.modules WHERE is_active = 1 ORDER BY module_name")
        modules = [{"module_id": str(r[0]), "module_code": r[1], "module_name": r[2]} for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT role_id, module_id FROM dbo.role_module_access WHERE is_active = 1")
        assignments = [{"role_id": str(r[0]), "module_id": str(r[1])} for r in cur.fetchall()]

        conn.close()
        return {"roles": roles, "modules": modules, "assignments": assignments}

    def role_exists(self, role_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.roles WHERE role_id = ?", role_id)
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def module_exists(self, module_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.modules WHERE module_id = ?", module_id)
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def assignment_active(self, role_id, module_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dbo.role_module_access WHERE role_id = ? AND module_id = ? AND is_active = 1",
            role_id, module_id
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def assign(self, role_id, module_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dbo.role_module_access WHERE role_id = ? AND module_id = ?",
            role_id, module_id
        )
        if cur.fetchone()[0] > 0:
            cur.execute(
                "UPDATE dbo.role_module_access SET is_active = 1, can_view = 1 WHERE role_id = ? AND module_id = ?",
                role_id, module_id
            )
        else:
            cur.execute(
                "INSERT INTO dbo.role_module_access (role_id, module_id, can_view, is_active) VALUES (?, ?, 1, 1)",
                role_id, module_id
            )
        conn.commit()
        conn.close()

    def remove(self, role_id, module_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.role_module_access SET is_active = 0 WHERE role_id = ? AND module_id = ?",
            role_id, module_id
        )
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected
