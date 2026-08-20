from __future__ import annotations

"""Mobile BFF business logic: session lifecycle and the dashboard aggregate."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config.security import EXPIRE_MINUTES, create_access_token
from services.auth_service import AuthService

from . import repository
from .schemas import DeviceInfo

# Bumped when the mobile contract changes in a way old builds cannot handle.
API_VERSION = "1.0.0"

# Oldest client build this server still accepts. Raise it to force an upgrade.
MIN_SUPPORTED_BUILD = 1
LATEST_BUILD = 1

FEATURES = [
    "auth.refresh",
    "auth.logout",
    "dashboard.aggregate",
]


class SessionError(Exception):
    """Refresh/logout failure carrying the reason the router should surface."""

    def __init__(self, message: str, *, reuse_detected: bool = False):
        super().__init__(message)
        self.message = message
        self.reuse_detected = reuse_detected


def _access_token_for(user: Dict[str, Any]) -> str:
    """Mints an access token with the same claim shape as /api/auth/login, so a
    token from either endpoint is interchangeable everywhere downstream."""
    roles = user.get("roles") or []
    primary_role = roles[0] if roles else {}
    return create_access_token(
        {
            "sub": user["user_id"],
            "username": user["username"],
            "tenant_id": user.get("tenant_id"),
            "is_platform_user": user.get("is_platform_user"),
            "role_names": [r["role_name"] for r in roles],
            "store_id": primary_role.get("store_id"),
            "store_code": primary_role.get("store_code"),
        }
    )


def _token_pair(
    user: Dict[str, Any],
    device: DeviceInfo,
    ip: Optional[str],
    replaces: Optional[str] = None,
    include_user: bool = True,
) -> Dict[str, Any]:
    refresh = repository.issue(
        user_id=user["user_id"],
        device_id=device.device_id,
        device_name=device.device_name,
        app_version=device.app_version,
        platform=device.platform,
        ip=ip,
        replaces=replaces,
    )
    payload = {
        "token": _access_token_for(user),
        "token_type": "bearer",
        "expires_in": EXPIRE_MINUTES * 60,
        "refresh_token": refresh["token"],
        "refresh_expires_in": repository.REFRESH_TOKEN_TTL_DAYS * 24 * 3600,
    }
    if include_user:
        payload["user"] = user
    return payload


def login(
    username: str,
    password: str,
    device: DeviceInfo,
    ip: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Authenticates and returns an access + refresh pair, or None on bad
    credentials. Reuses AuthService so password policy stays in one place."""
    user = AuthService().login(username, password)
    if not user:
        return None

    # One live chain per device: signing in again supersedes the old session
    # rather than accumulating tokens that stay valid for 30 days.
    repository.revoke_device(user["user_id"], device.device_id, "superseded-by-login")
    return _token_pair(user, device, ip)


def refresh(raw_token: str, device_id: str, ip: Optional[str] = None) -> Dict[str, Any]:
    """Exchanges a refresh token for a new pair, rotating the refresh token.

    Rotation plus reuse detection: because each token is single-use, a second
    presentation of an already-rotated token means the value leaked. In that
    case every live token for the device is revoked, forcing a real re-login.
    """
    record = repository.find(raw_token)
    if not record:
        raise SessionError("Invalid refresh token")

    if record["device_id"] != device_id:
        # A token replayed from a different install.
        repository.revoke_device(record["user_id"], record["device_id"], "device-mismatch")
        raise SessionError("Refresh token does not belong to this device", reuse_detected=True)

    if record["revoked_at"] is not None:
        repository.revoke_device(record["user_id"], record["device_id"], "reuse-detected")
        raise SessionError("Refresh token already used", reuse_detected=True)

    expires_at = record["expires_at"]
    if expires_at is not None:
        # Stored naive-UTC; compare in the same frame.
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        if expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise SessionError("Refresh token expired")

    user = AuthService().get_by_id(record["user_id"])
    if not user:
        # Deactivated or deleted between issue and refresh.
        repository.revoke_device(record["user_id"], record["device_id"], "user-inactive")
        raise SessionError("User is no longer active")

    repository.revoke(record["token_id"], "rotated")
    repository.touch(record["token_id"])

    device = DeviceInfo(device_id=device_id)
    return _token_pair(user, device, ip, replaces=record["token_id"], include_user=True)


def logout(
    user_id: str,
    raw_token: Optional[str] = None,
    device_id: Optional[str] = None,
    all_devices: bool = False,
) -> int:
    """Revokes refresh tokens. Returns how many were revoked.

    Access tokens remain valid until they expire — they are stateless and this
    codebase has no denylist. The refresh chain is what logout actually ends.
    """
    if all_devices:
        revoked = 0
        for device in repository.list_devices(user_id):
            revoked += repository.revoke_device(user_id, device["device_id"], "logout-all")
        return revoked

    if raw_token:
        record = repository.find(raw_token)
        if record and record["user_id"] == user_id:
            return repository.revoke_device(user_id, record["device_id"], "logout")
        return 0

    if device_id:
        return repository.revoke_device(user_id, device_id, "logout")

    return 0


def handshake() -> Dict[str, Any]:
    return {
        "api_version": API_VERSION,
        "min_supported_build": MIN_SUPPORTED_BUILD,
        "latest_build": LATEST_BUILD,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES,
    }
