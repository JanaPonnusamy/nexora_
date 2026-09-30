from pathlib import Path

from repositories.store_repository import StoreRepository
from services.store_crypto_service import StoreCryptoService

# Same Fernet key the store agent bundles and the runtime uses to decrypt the
# store DB password (see store_agent/config/fernet.key, backend/scripts/
# _live_store_conn.py, modules/licensing/db_resolver.py). Stable since
# 2026-06-20; encrypting here with a different key would make the agent unable
# to decrypt.
_FERNET_KEY_FILE = Path(__file__).resolve().parents[2] / "store_agent" / "config" / "fernet.key"


class StoreService:

    def get_all(self):
        return StoreRepository().get_all()

    def get_by_id(self, store_id):
        return StoreRepository().get_by_id(store_id)

    def get_by_tenant(self, tenant_id):
        return StoreRepository().get_by_tenant(tenant_id)

    def get_agent_config(self, store_id):
        return StoreRepository().get_agent_config(store_id)

    def store_code_exists(self, store_code, tenant_id, exclude_id=None):
        return StoreRepository().store_code_exists(store_code, tenant_id, exclude_id)

    def create(self, tenant_id, store_code, store_name, server_name, database_name):
        return StoreRepository().create(tenant_id, store_code, store_name, server_name, database_name)

    def update(self, store_id, tenant_id, store_code, store_name, server_name, database_name):
        return StoreRepository().update(store_id, tenant_id, store_code, store_name, server_name, database_name)

    def set_active(self, store_id, is_active):
        return StoreRepository().set_active(store_id, is_active)

    def get_connection_details(self, store_id):
        return StoreRepository().get_connection_details(store_id)

    def update_credentials(self, store_id, server_name, database_name, username,
                           connection_type, password=None):
        """Persist DB connection details. When password is a non-empty string it
        is Fernet-encrypted into password_encrypted; when None/blank the stored
        password is left untouched (edit server/username without re-typing it)."""
        update_password = bool(password)
        password_encrypted = None
        if update_password:
            key = _FERNET_KEY_FILE.read_bytes()
            password_encrypted = StoreCryptoService.encrypt_password(password, key)
        return StoreRepository().update_credentials(
            store_id,
            (server_name or "").strip() or None,
            (database_name or "").strip() or None,
            (username or "").strip() or None,
            (connection_type or "").strip() or None,
            password_encrypted=password_encrypted,
            update_password=update_password,
        )