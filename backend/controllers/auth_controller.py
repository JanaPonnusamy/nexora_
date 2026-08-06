
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from dtos.login_request import LoginRequest
from services.auth_service import AuthService
from config.security import create_access_token, create_setup_token, setup_access_checksum
from dependencies.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
_SETUP_USERNAME = os.getenv("UNINEX_SETUP_USERNAME", "setupdeploy")
_SETUP_PASSWORD = os.getenv("UNINEX_SETUP_PASSWORD", "")
_SETUP_ALLOWED_PATHS = [
    "/api/tenants",
    "/api/stores",
    "/api/stores/tenant/{tenant_id}",
    "/api/stores/{store_id}/agent-config",
]

@router.post("/login")
def login(req: LoginRequest):
    if req.username.strip().lower() == _SETUP_USERNAME.lower():
        raise HTTPException(status_code=403, detail="Setup deploy user is restricted to setup provisioning only")
    user = AuthService().login(req.username, req.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid Username Or Password")

    token = create_access_token({
        "sub": user["user_id"],
        "username": user["username"],
        "tenant_id": user["tenant_id"],
        "is_platform_user": user["is_platform_user"],
        "role_names": [r["role_name"] for r in user["roles"]],
    })

    return {"token": token, "token_type": "bearer", "user": user}


@router.post("/setup-login")
def setup_login(req: LoginRequest, x_nexora_setup_checksum: str | None = Header(default=None)):
    if not _SETUP_PASSWORD:
        raise HTTPException(status_code=503, detail="Setup provisioning access is not configured on this HO")
    if req.username.strip().lower() != _SETUP_USERNAME.lower():
        raise HTTPException(status_code=401, detail="Invalid setup credentials")
    expected_checksum = setup_access_checksum(
        _SETUP_USERNAME,
        _SETUP_PASSWORD,
        allowed_paths=_SETUP_ALLOWED_PATHS,
    )
    if not x_nexora_setup_checksum or x_nexora_setup_checksum != expected_checksum:
        raise HTTPException(status_code=401, detail="Invalid setup checksum")

    user = AuthService().login(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid setup credentials")

    token = create_setup_token({
        "sub": user["user_id"],
        "username": user["username"],
        "tenant_id": user["tenant_id"],
        "aud": "store_agent_setup",
        "allowed_paths": _SETUP_ALLOWED_PATHS,
    })
    return {
        "token": token,
        "token_type": "setup-bearer",
        "scope": "setup_readonly",
        "allowed_paths": _SETUP_ALLOWED_PATHS,
        "checksum": expected_checksum,
    }

@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    user = AuthService().get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Not Found")
    return user
