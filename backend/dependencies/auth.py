from __future__ import annotations

import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from config.security import decode_access_token
from repositories.user_repository import UserRepository

# Roles that bypass per-module permission checks entirely and always see
# every module, including ones added later with no role_module_access rows
# seeded yet (see UserRepository.get_user_modules).
FULL_ACCESS_ROLES = {"SUPER_ADMIN", "PLATFORM_OWNER"}

_bearer = HTTPBearer(auto_error=False)

# In-memory throttle so the per-request session heart-beat writes to the DB at
# most once per user per this many seconds (a busy client fires many requests).
_HEARTBEAT_THROTTLE_SECONDS = 60
_last_heartbeat: dict[str, float] = {}


def _enforce_active_session(claims: dict) -> None:
    """Single active session per user. A token carries the session id (sid) it
    was minted with; if that no longer matches the user's current session, this
    token was superseded (someone took the session over after its lease lapsed)
    and is rejected. While the sid is valid, refresh the lease (throttled)."""
    sid = claims.get("sid")
    user_id = claims.get("sub")
    # Legacy tokens minted before this feature carry no sid - don't enforce.
    if not sid or not user_id:
        return
    repo = UserRepository()
    stored = repo.get_active_session_id(user_id)
    if stored is None:
        return
    if stored != sid:
        raise HTTPException(status_code=401, detail="Signed in on another system")
    now = time.monotonic()
    last = _last_heartbeat.get(user_id, 0.0)
    if now - last >= _HEARTBEAT_THROTTLE_SECONDS:
        _last_heartbeat[user_id] = now
        repo.touch_active_session(user_id, sid)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    _enforce_active_session(claims)
    return claims


def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict | None:
    """Like get_current_user, but returns None instead of 401 when no bearer
    token is present at all - for endpoints also reachable via the store-agent
    setup token (app.py's _SETUP_READ_PATTERNS), which authenticates via the
    x-nexora-setup-token header, not a JWT bearer. A bearer token that IS
    present still has to be valid; only its absence is tolerated here."""
    if not credentials:
        return None
    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def has_full_access(user: dict) -> bool:
    return bool(user.get("is_platform_user")) or any(
        r in FULL_ACCESS_ROLES for r in user.get("role_names", [])
    )
