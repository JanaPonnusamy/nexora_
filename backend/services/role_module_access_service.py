from repositories.role_module_access_repository import RoleModuleAccessRepository

class RoleModuleAccessService:

    def seed_super_admin_permissions(self):
        return RoleModuleAccessRepository().seed_super_admin_permissions()

    def get_role_permission_matrix(self, role_id):
        return RoleModuleAccessRepository().get_role_permission_matrix(role_id)

    # ----- permission matrix (role <-> module assignment) -----

    def get_matrix(self):
        return RoleModuleAccessRepository().get_matrix()

    def role_exists(self, role_id):
        return RoleModuleAccessRepository().role_exists(role_id)

    def module_exists(self, module_id):
        return RoleModuleAccessRepository().module_exists(module_id)

    def assignment_active(self, role_id, module_id):
        return RoleModuleAccessRepository().assignment_active(role_id, module_id)

    def assign(self, role_id, module_id):
        return RoleModuleAccessRepository().assign(role_id, module_id)

    def remove(self, role_id, module_id):
        return RoleModuleAccessRepository().remove(role_id, module_id)
