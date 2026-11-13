from __future__ import annotations

from fastapi import APIRouter, Depends
from services.role_module_access_service import RoleModuleAccessService
from dependencies.store_scope import require_super_admin

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.post("/seed")
def seed_permissions(current_user: dict = Depends(require_super_admin)):
    return RoleModuleAccessService().seed_super_admin_permissions()

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str, current_user: dict = Depends(require_super_admin)):
    return RoleModuleAccessService().get_role_permission_matrix(role_id)
