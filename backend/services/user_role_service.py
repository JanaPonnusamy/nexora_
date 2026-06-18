
from repositories.user_role_repository import UserRoleRepository

class UserRoleService:

    def seed(self):
        return UserRoleRepository().seed_superadmin_assignment()

    def get_roles(self, user_id):
        rows = UserRoleRepository().get_user_roles(user_id)

        return [{
            "role_id": str(r[0]),
            "role_name": r[1],
            "store_id": str(r[2]),
            "store_code": r[3],
            "store_name": r[4]
        } for r in rows]
