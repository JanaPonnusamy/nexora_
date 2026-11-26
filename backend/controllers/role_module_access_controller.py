from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from services.role_module_access_service import RoleModuleAccessService
from dependencies.store_scope import require_super_admin
from dtos.role_module_access_request import RoleModuleAccessRequest
from modules.audit.writer import record_audit
from modules.audit.context import AuditContext

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.post("/seed")
def seed_permissions(current_user: dict = Depends(require_super_admin)):
    return RoleModuleAccessService().seed_super_admin_permissions()

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str, current_user: dict = Depends(require_super_admin)):
    return RoleModuleAccessService().get_role_permission_matrix(role_id)

@router.get("/matrix")
def get_matrix(current_user: dict = Depends(require_super_admin)):
    return RoleModuleAccessService().get_matrix()

@router.put("")
def set_permissions(body: RoleModuleAccessRequest, request: Request, current_user: dict = Depends(require_super_admin)):
    svc = RoleModuleAccessService()
    if not svc.role_exists(body.role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    if not svc.module_exists(body.module_id):
        raise HTTPException(status_code=404, detail="Module Not Found")
    svc.set_permissions(
        body.role_id, body.module_id,
        body.can_view, body.can_create, body.can_edit, body.can_delete, body.can_export,
    )
    matrix = svc.get_role_permission_matrix(body.role_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role_module_access.update",
        category="role",
        target_type="role_module_access",
        target_id=f"{body.role_id}:{body.module_id}",
        reason=f"Updated module permissions for role {body.role_id} / module {body.module_id}",
        metadata={
            "role_id": body.role_id, "module_id": body.module_id,
            "can_view": body.can_view, "can_create": body.can_create,
            "can_edit": body.can_edit, "can_delete": body.can_delete,
            "can_export": body.can_export,
        },
    )
    return matrix
