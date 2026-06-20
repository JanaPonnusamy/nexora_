
from fastapi import APIRouter, HTTPException
from services.user_service import UserService
from dtos.user_request import UserRequest, UserStatusRequest

router = APIRouter(prefix="/api/users", tags=["Users"])
relations_router = APIRouter(tags=["Users"])

def _serialize_list(r):
    return {
        "user_id": str(r[0]),
        "username": r[1],
        "full_name": r[2],
        "tenant_id": str(r[3]) if r[3] else None,
        "tenant_name": r[4],
        "is_active": bool(r[5]),
        "last_login": r[6].isoformat() if r[6] else None,
        "store_count": int(r[7]) if r[7] is not None else 0,
        "role_count": int(r[8]) if r[8] is not None else 0,
    }

def _serialize_detail(r):
    return {
        "user_id": str(r[0]),
        "username": r[1],
        "full_name": r[2],
        "first_name": r[3],
        "last_name": r[4],
        "email": r[5],
        "mobile": r[6],
        "tenant_id": str(r[7]) if r[7] else None,
        "tenant_name": r[8],
        "is_platform_user": bool(r[9]),
        "is_active": bool(r[10]),
        "last_login": r[11].isoformat() if r[11] else None,
        "store_count": int(r[12]) if r[12] is not None else 0,
        "role_count": int(r[13]) if r[13] is not None else 0,
    }

@router.get("")
def get_users(
    search: str | None = None,
    tenant_id: str | None = None,
    store_id: str | None = None,
    role_id: str | None = None,
    status: str | None = None,
):
    rows = UserService().get_all(search, tenant_id, store_id, role_id, status)
    return [_serialize_list(r) for r in rows]

@router.get("/{user_id}")
def get_user(user_id: str):
    r = UserService().get_by_id(user_id)
    if not r:
        raise HTTPException(status_code=404, detail="User Not Found")
    return _serialize_detail(r)

@router.post("", status_code=201)
def create_user(body: UserRequest):
    username = body.username.strip()
    full_name = body.full_name.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required")
    if not body.password or not body.password.strip():
        raise HTTPException(status_code=400, detail="Password is required")
    if UserService().username_exists(username):
        raise HTTPException(status_code=400, detail="Username already exists")
    new_id = UserService().create(username, full_name, body.password)
    r = UserService().get_by_id(str(new_id))
    return _serialize_detail(r)

@router.put("/{user_id}")
def update_user(user_id: str, body: UserRequest):
    username = body.username.strip()
    full_name = body.full_name.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required")
    if not UserService().get_by_id(user_id):
        raise HTTPException(status_code=404, detail="User Not Found")
    if UserService().username_exists(username, user_id):
        raise HTTPException(status_code=400, detail="Username already exists")
    UserService().update(user_id, username, full_name)
    r = UserService().get_by_id(user_id)
    return _serialize_detail(r)

@router.patch("/{user_id}/status")
def set_user_status(user_id: str, body: UserStatusRequest):
    if not UserService().get_by_id(user_id):
        raise HTTPException(status_code=404, detail="User Not Found")
    UserService().set_active(user_id, body.is_active)
    r = UserService().get_by_id(user_id)
    return _serialize_detail(r)

@relations_router.get("/api/tenants/{tenant_id}/users")
def get_users_by_tenant(tenant_id: str):
    rows = UserService().get_all(tenant_id=tenant_id)
    return [_serialize_list(r) for r in rows]

@relations_router.get("/api/stores/{store_id}/users")
def get_users_by_store(store_id: str):
    rows = UserService().get_all(store_id=store_id)
    return [_serialize_list(r) for r in rows]
