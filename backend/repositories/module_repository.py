
from config.database import get_connection
import uuid

class ModuleRepository:

    def seed_modules(self):
        return 0

    def get_all_modules(self):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            'SELECT module_id,module_code,module_name,description,is_active FROM dbo.modules ORDER BY module_name'
        )

        rows = cur.fetchall()
        conn.close()

        result = []

        for row in rows:
            result.append({
                'module_id': str(row[0]),
                'module_code': row[1],
                'module_name': row[2],
                'description': row[3],
                'is_active': bool(row[4])
            })

        return result

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

        return {
            'module_id': str(row[0]),
            'module_code': row[1],
            'module_name': row[2],
            'description': row[3],
            'is_active': bool(row[4])
        }
