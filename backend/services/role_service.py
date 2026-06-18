
from repositories.role_repository import RoleRepository

class RoleService:

    def seed_roles(self):
        return RoleRepository().seed_roles()

    def get_all(self):
        rows = RoleRepository().get_all_roles()

        return [
            {
                "role_id": str(r[0]),
                "role_name": r[1],
                "description": r[2],
                "is_active": bool(r[3])
            }
            for r in rows
        ]

    def get_by_id(self, role_id):
        r = RoleRepository().get_role_by_id(role_id)

        if not r:
            return None

        return {
            "role_id": str(r[0]),
            "role_name": r[1],
            "description": r[2],
            "is_active": bool(r[3])
        }
