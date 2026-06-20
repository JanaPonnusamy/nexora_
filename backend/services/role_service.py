
from repositories.role_repository import RoleRepository

class RoleService:

    def seed_roles(self):
        return RoleRepository().seed_roles()

    def get_all(self, search=None, status=None):
        rows = RoleRepository().get_all_roles(search, status)
        return [self._serialize(r) for r in rows]

    def get_by_id(self, role_id):
        r = RoleRepository().get_role_by_id(role_id)
        if not r:
            return None
        return self._serialize(r)

    def role_name_exists(self, role_name, exclude_id=None):
        return RoleRepository().role_name_exists(role_name, exclude_id)

    def create(self, role_name, description):
        return RoleRepository().create(role_name, description)

    def update(self, role_id, role_name, description):
        return RoleRepository().update(role_id, role_name, description)

    def set_active(self, role_id, is_active):
        return RoleRepository().set_active(role_id, is_active)

    @staticmethod
    def _serialize(r):
        return {
            "role_id": str(r[0]),
            "role_name": r[1],
            "description": r[2],
            "is_active": bool(r[3]),
            "assigned_users": int(r[4]) if r[4] is not None else 0,
        }
