
from __future__ import annotations

from fastapi import APIRouter
from services.user_role_service import UserRoleService

router = APIRouter(prefix="/api/user-roles", tags=["User Roles"])

@router.post("/seed")
def seed():
    count = UserRoleService().seed()
    return {"status":"success","assignments_created":count}

@router.post("/seed-defaults")
def seed_defaults():
    count = UserRoleService().seed_defaults()
    return {"status":"success","assignments_created":count}

@router.post("/seed-role-users")
def seed_role_users():
    """Creates one login per role (superadmin/platformowner/tenantadmin/
    storeadmin/storemanager/storeuser/syncoperator), all password Nexora@123,
    so every access level has a ready-made account. Safe to call repeatedly -
    existing usernames are left alone and just get their role assignment
    checked."""
    count = UserRoleService().seed_all_role_users()
    return {"status":"success","users_created":count}

@router.get("/user/{user_id}")
def get_user_roles(user_id:str):
    return UserRoleService().get_roles(user_id)
