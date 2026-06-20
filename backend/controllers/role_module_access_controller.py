from fastapi import APIRouter
from services.role_module_access_service import RoleModuleAccessService

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.post("/seed")
def seed_permissions():
    return RoleModuleAccessService().seed_super_admin_permissions()

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str):
    return RoleModuleAccessService().get_role_permission_matrix(role_id)
