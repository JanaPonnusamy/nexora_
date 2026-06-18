
from fastapi import APIRouter
from services.role_module_access_service import RoleModuleAccessService

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str):
    return RoleModuleAccessService().get_role_permission_matrix(role_id)
