
import bcrypt
from repositories.user_repository import UserRepository

class UserService:

    def get_all(self, search=None, tenant_id=None, store_id=None, role_id=None, status=None):
        return UserRepository().get_all(search, tenant_id, store_id, role_id, status)

    def get_by_id(self, user_id):
        return UserRepository().get_by_id(user_id)

    def username_exists(self, username, exclude_id=None):
        return UserRepository().username_exists(username, exclude_id)

    def create(self, username, full_name, password):
        first_name, last_name = self._split_name(full_name)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return UserRepository().create(username, first_name, last_name, password_hash)

    def update(self, user_id, username, full_name):
        first_name, last_name = self._split_name(full_name)
        return UserRepository().update(user_id, username, first_name, last_name)

    def set_active(self, user_id, is_active):
        return UserRepository().set_active(user_id, is_active)

    @staticmethod
    def _split_name(full_name):
        parts = full_name.strip().split(' ', 1)
        first_name = parts[0]
        last_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        return first_name, last_name
