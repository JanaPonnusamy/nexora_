
from fastapi import APIRouter, HTTPException
from services.role_service import RoleService
from dtos.role_request import RoleRequest, RoleStatusRequest

router = APIRouter(prefix="/api/roles", tags=["Roles"])

@router.post("/seed")
def seed_roles():
    count = RoleService().seed_roles()
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
def create_role(body: RoleRequest):
    role_name = body.role_name.strip()
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")
    if RoleService().role_name_exists(role_name):
        raise HTTPException(status_code=400, detail="Role name already exists")
    description = body.description.strip() if body.description else None
    new_id = RoleService().create(role_name, description)
    return RoleService().get_by_id(str(new_id))

@router.put("/{role_id}")
def update_role(role_id:str, body: RoleRequest):
    role_name = body.role_name.strip()
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")
    if not RoleService().get_by_id(role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    if RoleService().role_name_exists(role_name, role_id):
        raise HTTPException(status_code=400, detail="Role name already exists")
    description = body.description.strip() if body.description else None
    RoleService().update(role_id, role_name, description)
    return RoleService().get_by_id(role_id)

@router.patch("/{role_id}/status")
def set_role_status(role_id:str, body: RoleStatusRequest):
    if not RoleService().get_by_id(role_id):
        raise HTTPException(status_code=404, detail="Role Not Found")
    RoleService().set_active(role_id, body.is_active)
    return RoleService().get_by_id(role_id)
