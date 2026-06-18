
from fastapi import APIRouter
from services.role_service import RoleService

router = APIRouter(prefix="/api/roles", tags=["Roles"])

@router.post("/seed")
def seed_roles():
    count = RoleService().seed_roles()
    return {"status":"success","roles_created":count}

@router.get("")
def get_roles():
    return RoleService().get_all()

@router.get("/{role_id}")
def get_role(role_id:str):
    return RoleService().get_by_id(role_id)
