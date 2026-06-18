
from repositories.tenant_repository import TenantRepository

class TenantService:
    def get_all(self):
        return TenantRepository().get_all()

    def get_by_id(self, tenant_id):
        return TenantRepository().get_by_id(tenant_id)
