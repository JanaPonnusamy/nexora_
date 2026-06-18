
from fastapi import APIRouter
from services.user_role_service import UserRoleService

router = APIRouter(prefix="/api/user-roles", tags=["User Roles"])

@router.post("/seed")
def seed():
    count = UserRoleService().seed()
    return {"status":"success","assignments_created":count}

@router.get("/user/{user_id}")
def get_user_roles(user_id:str):
    return UserRoleService().get_roles(user_id)
