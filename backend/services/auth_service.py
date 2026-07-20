
import bcrypt
from repositories.user_repository import UserRepository

class AuthService:

    def login(self, username, password):
        repo = UserRepository()
        user = repo.get_user_by_username(username)

        if not user:
            return None

        if not bool(user[5]):
            return None

        if not bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
            return None

        repo.update_last_login(user[0])
        modules = repo.get_user_modules(user[0])
        roles = repo.get_user_roles(user[0])

        return {
            "user_id": str(user[0]),
            "username": user[1],
            "first_name": user[3],
            "is_platform_user": bool(user[4]),
            "is_active": bool(user[5]),
            "tenant_id": str(user[6]) if user[6] else None,
            "modules": [
                {
                    "module": r[0],
                    "name": r[1],
                    "can_view": bool(r[2]),
                    "can_create": bool(r[3]),
                    "can_edit": bool(r[4]),
                    "can_delete": bool(r[5]),
                    "can_export": bool(r[6])
                }
                for r in modules
            ],
            "roles": [
                {
                    "role_id": str(r[0]),
                    "role_name": r[1],
                    "store_id": str(r[2]),
                    "store_code": r[3],
                    "store_name": r[4]
                }
                for r in roles
            ]
        }
