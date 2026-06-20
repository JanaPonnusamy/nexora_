
from config.database import get_connection

class ModuleRepository:

    def seed_modules(self):
        return 0

    def get_all_modules(self, search=None, status=None):
        conn = get_connection()
        cur = conn.cursor()

        where = []
        params = []
        if search:
            where.append("(module_code LIKE ? OR module_name LIKE ? OR description LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if status == 'active':
            where.append("is_active = 1")
        elif status == 'inactive':
            where.append("is_active = 0")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        cur.execute(f"""
        SELECT module_id,module_code,module_name,description,is_active
        FROM dbo.modules
        {where_sql}
        ORDER BY module_name
        """, params)

        rows = cur.fetchall()
        conn.close()
        return [self._serialize(r) for r in rows]

    def get_module_by_id(self, module_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            'SELECT module_id,module_code,module_name,description,is_active FROM dbo.modules WHERE module_id=?',
            module_id
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self._serialize(row)

    def module_code_exists(self, module_code, exclude_id=None):
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute("SELECT COUNT(*) FROM dbo.modules WHERE module_code = ? AND module_id <> ?", module_code, exclude_id)
        else:
            cur.execute("SELECT COUNT(*) FROM dbo.modules WHERE module_code = ?", module_code)
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def create(self, module_code, module_name, description):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO dbo.modules (module_id, module_code, module_name, description, is_active)
        OUTPUT INSERTED.module_id
        VALUES (NEWID(), ?, ?, ?, 1)
        """, module_code, module_name, description)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update(self, module_id, module_code, module_name, description):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.modules
        SET module_code = ?, module_name = ?, description = ?
        WHERE module_id = ?
        """, module_code, module_name, description, module_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_active(self, module_id, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.modules
        SET is_active = ?
        WHERE module_id = ?
        """, 1 if is_active else 0, module_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    @staticmethod
    def _serialize(row):
        return {
            'module_id': str(row[0]),
            'module_code': row[1],
            'module_name': row[2],
            'description': row[3],
            'is_active': bool(row[4])
        }
