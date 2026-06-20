
from fastapi import APIRouter, HTTPException
from services.role_module_access_service import RoleModuleAccessService
from dtos.permission_request import PermissionAssignRequest

router = APIRouter(prefix="/api/permissions", tags=["Permissions"])

@router.get("/matrix")
def get_matrix():
    return RoleModuleAccessService().get_matrix()

@router.post("/assign")
def assign_permission(body: PermissionAssignRequest):
    svc = RoleModuleAccessService()
    if not svc.role_exists(body.role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    if not svc.module_exists(body.module_id):
        raise HTTPException(status_code=404, detail="Module Not Found")
    if svc.assignment_active(body.role_id, body.module_id):
        raise HTTPException(status_code=400, detail="Assignment already exists")
    svc.assign(body.role_id, body.module_id)
    return {"success": True, "message": "Module assigned to role"}

@router.delete("/assign")
def remove_permission(body: PermissionAssignRequest):
    svc = RoleModuleAccessService()
    if not svc.role_exists(body.role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    if not svc.module_exists(body.module_id):
        raise HTTPException(status_code=404, detail="Module Not Found")
    svc.remove(body.role_id, body.module_id)
    return {"success": True, "message": "Module access removed"}
