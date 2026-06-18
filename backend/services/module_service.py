
from repositories.module_repository import ModuleRepository

class ModuleService:

    def seed_modules(self):
        return ModuleRepository().seed_modules()

    def get_all(self):
        return ModuleRepository().get_all_modules()

    def get_by_id(self, module_id):
        return ModuleRepository().get_module_by_id(module_id)
