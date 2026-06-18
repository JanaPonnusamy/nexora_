
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

        return {
            "user_id": str(user[0]),
            "username": user[1],
            "first_name": user[3],
            "is_platform_user": bool(user[4]),
            "is_active": bool(user[5])
        }
