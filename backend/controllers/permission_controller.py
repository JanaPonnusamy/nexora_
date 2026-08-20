
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from services.role_module_access_service import RoleModuleAccessService
from dtos.permission_request import PermissionAssignRequest
from dependencies.auth import get_current_user
from modules.audit.writer import record_audit
from modules.audit.context import AuditContext

router = APIRouter(prefix="/api/permissions", tags=["Permissions"])

@router.get("/matrix")
def get_matrix():
    return RoleModuleAccessService().get_matrix()

@router.post("/assign")
def assign_permission(body: PermissionAssignRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = RoleModuleAccessService()
    if not svc.role_exists(body.role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    if not svc.module_exists(body.module_id):
        raise HTTPException(status_code=404, detail="Module Not Found")
    if svc.assignment_active(body.role_id, body.module_id):
        raise HTTPException(status_code=400, detail="Assignment already exists")
    svc.assign(body.role_id, body.module_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role.permission.assign",
        category="role",
        target_type="role_module_access",
        target_id=f"{body.role_id}:{body.module_id}",
        target_label=f"Role {body.role_id} -> Module {body.module_id}",
        reason=f"Assigned module {body.module_id} to role {body.role_id}",
        metadata={"role_id": body.role_id, "module_id": body.module_id},
    )

    return {"success": True, "message": "Module assigned to role"}

@router.delete("/assign")
def remove_permission(body: PermissionAssignRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = RoleModuleAccessService()
    if not svc.role_exists(body.role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    if not svc.module_exists(body.module_id):
        raise HTTPException(status_code=404, detail="Module Not Found")
    svc.remove(body.role_id, body.module_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role.permission.remove",
        category="role",
        target_type="role_module_access",
        target_id=f"{body.role_id}:{body.module_id}",
        target_label=f"Role {body.role_id} -> Module {body.module_id}",
        reason=f"Revoked module {body.module_id} from role {body.role_id}",
        metadata={"role_id": body.role_id, "module_id": body.module_id},
    )

    return {"success": True, "message": "Module access removed"}
