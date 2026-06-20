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