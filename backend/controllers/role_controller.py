
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from services.role_service import RoleService
from dtos.role_request import RoleRequest, RoleStatusRequest
from dependencies.auth import get_current_user
from modules.audit.writer import record_audit
from modules.audit.diff import compute_mutation_diff
from modules.audit.context import AuditContext

router = APIRouter(prefix="/api/roles", tags=["Roles"])

@router.post("/seed")
def seed_roles(request: Request, current_user: dict = Depends(get_current_user)):
    count = RoleService().seed_roles()
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role.seed",
        category="role",
        target_type="roles",
        reason=f"Seeded default system roles ({count} created)",
        metadata={"roles_created": count},
    )
    return {"status":"success","roles_created":count}

@router.get("")
def get_roles(search: str | None = None, status: str | None = None):
    return RoleService().get_all(search, status)

@router.get("/{role_id}")
def get_role(role_id:str):
    r = RoleService().get_by_id(role_id)
    if not r:
        raise HTTPException(status_code=404, detail="Role Not Found")
    return r

@router.post("", status_code=201)
def create_role(body: RoleRequest, request: Request, current_user: dict = Depends(get_current_user)):
    role_name = body.role_name.strip()
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")
    if RoleService().role_name_exists(role_name):
        raise HTTPException(status_code=400, detail="Role name already exists")
    description = body.description.strip() if body.description else None
    new_id = RoleService().create(role_name, description)
    res = RoleService().get_by_id(str(new_id))

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role.create",
        target_type="role",
        target_id=str(new_id),
        target_label=role_name,
        reason=f"Created role '{role_name}'",
        metadata={"role_name": role_name, "description": description},
    )
    return res

@router.put("/{role_id}")
def update_role(role_id:str, body: RoleRequest, request: Request, current_user: dict = Depends(get_current_user)):
    role_name = body.role_name.strip()
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")
    existing = RoleService().get_by_id(role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Role Not Found")
    if RoleService().role_name_exists(role_name, role_id):
        raise HTTPException(status_code=400, detail="Role name already exists")
    description = body.description.strip() if body.description else None

    changed_fields, diff_details = compute_mutation_diff(
        dict(existing) if isinstance(existing, dict) else {"role_name": existing[1] if len(existing)>1 else None},
        {"role_name": role_name, "description": description},
    )
    changed_str = ", ".join(changed_fields) if changed_fields else "no field changes"

    RoleService().update(role_id, role_name, description)
    res = RoleService().get_by_id(role_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role.update",
        target_type="role",
        target_id=role_id,
        target_label=role_name,
        reason=f"Updated role '{role_name}' (changed: {changed_str})",
        metadata={"diff": diff_details, "changed_fields": changed_fields},
    )
    return res

@router.patch("/{role_id}/status")
def set_role_status(role_id:str, body: RoleStatusRequest, request: Request, current_user: dict = Depends(get_current_user)):
    existing = RoleService().get_by_id(role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Role Not Found")
    RoleService().set_active(role_id, body.is_active)
    res = RoleService().get_by_id(role_id)

    verb = "Activated" if body.is_active else "Deactivated"
    role_name = str(existing.get("role_name") if isinstance(existing, dict) else role_id)
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="role.status.update",
        target_type="role",
        target_id=role_id,
        target_label=role_name,
        reason=f"{verb} role '{role_name}'",
        metadata={"is_active": body.is_active},
    )
    return res
