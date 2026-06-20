
from repositories.module_repository import ModuleRepository

class ModuleService:

    def seed_modules(self):
        return ModuleRepository().seed_modules()

    def get_all(self, search=None, status=None):
        return ModuleRepository().get_all_modules(search, status)

    def get_by_id(self, module_id):
        return ModuleRepository().get_module_by_id(module_id)

    def module_code_exists(self, module_code, exclude_id=None):
        return ModuleRepository().module_code_exists(module_code, exclude_id)

    def create(self, module_code, module_name, description):
        return ModuleRepository().create(module_code, module_name, description)

    def update(self, module_id, module_code, module_name, description):
        return ModuleRepository().update(module_id, module_code, module_name, description)

    def set_active(self, module_id, is_active):
        return ModuleRepository().set_active(module_id, is_active)
