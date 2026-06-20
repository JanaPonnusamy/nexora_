
from repositories.tenant_repository import TenantRepository

class TenantService:
    def get_all(self):
        return TenantRepository().get_all()

    def get_by_id(self, tenant_id):
        return TenantRepository().get_by_id(tenant_id)

    def create(self, tenant_code, tenant_abbreviation, tenant_name, db_name):
        return TenantRepository().create(tenant_code, tenant_abbreviation, tenant_name, db_name)

    def update(self, tenant_id, tenant_code, tenant_abbreviation, tenant_name, db_name):
        return TenantRepository().update(tenant_id, tenant_code, tenant_abbreviation, tenant_name, db_name)

    def set_active(self, tenant_id, is_active):
        return TenantRepository().set_active(tenant_id, is_active)
