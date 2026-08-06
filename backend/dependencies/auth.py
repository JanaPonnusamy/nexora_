from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from config.security import decode_access_token

# Roles that bypass per-module permission checks entirely and always see
# every module, including ones added later with no role_module_access rows
# seeded yet (see UserRepository.get_user_modules).
FULL_ACCESS_ROLES = {"SUPER_ADMIN", "PLATFORM_OWNER"}

_bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return claims


def has_full_access(user: dict) -> bool:
    return bool(user.get("is_platform_user")) or any(
        r in FULL_ACCESS_ROLES for r in user.get("role_names", [])
    )
