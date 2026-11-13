
from __future__ import annotations

from fastapi import APIRouter, Depends
from services.user_role_service import UserRoleService
from dependencies.auth import get_current_user
from dependencies.store_scope import require_super_admin, has_unrestricted_scope
from fastapi import HTTPException

router = APIRouter(prefix="/api/user-roles", tags=["User Roles"])

@router.post("/seed")
def seed(current_user: dict = Depends(require_super_admin)):
    count = UserRoleService().seed()
    return {"status":"success","assignments_created":count}

@router.post("/seed-defaults")
def seed_defaults(current_user: dict = Depends(require_super_admin)):
    count = UserRoleService().seed_defaults()
    return {"status":"success","assignments_created":count}

@router.post("/seed-role-users")
def seed_role_users(current_user: dict = Depends(require_super_admin)):
    """Creates one login per role (superadmin/platformowner/tenantadmin/
    storeadmin/storemanager/storeuser/syncoperator), all password Nexora@123,
    so every access level has a ready-made account. Safe to call repeatedly -
    existing usernames are left alone and just get their role assignment
    checked. Super-admin only - this mints standing accounts with a known,
    fixed password."""
    count = UserRoleService().seed_all_role_users()
    return {"status":"success","users_created":count}

@router.get("/user/{user_id}")
def get_user_roles(user_id:str, current_user: dict = Depends(get_current_user)):
    # A non-super-admin may only review their own role assignment.
    if not has_unrestricted_scope(current_user) and str(current_user.get("sub") or "") != str(user_id):
        raise HTTPException(status_code=403, detail="You do not have access to this user's roles.")
    return UserRoleService().get_roles(user_id)
