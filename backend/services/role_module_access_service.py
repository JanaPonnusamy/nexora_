
from repositories.role_module_access_repository import RoleModuleAccessRepository

class RoleModuleAccessService:

    def get_role_permission_matrix(self, role_id):
        return RoleModuleAccessRepository().get_role_permission_matrix(role_id)
