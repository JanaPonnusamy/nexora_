from repositories.store_repository import StoreRepository

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