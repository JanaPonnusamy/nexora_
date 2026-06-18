
from fastapi import APIRouter
from dtos.login_request import LoginRequest
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

_current_user = None

@router.post("/login")
def login(req: LoginRequest):
    global _current_user

    user = AuthService().login(req.username, req.password)

    if not user:
        return {"error":"Invalid Username Or Password"}

    _current_user = user
    return user

@router.get("/me")
def me():
    return _current_user if _current_user else {"error":"Not Logged In"}
