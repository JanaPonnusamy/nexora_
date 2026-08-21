
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from dtos.login_request import LoginRequest
from services.auth_service import AuthService
from config.security import create_access_token, create_setup_token, setup_access_checksum
from dependencies.auth import get_current_user
from repositories.user_repository import UserRepository
from modules.audit.writer import record_audit, record_audit_strict
from modules.audit.models import ActorRole, AuditStatus

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
# Single active session per user: a login is blocked while another session is
# still alive (heart-beating within this many minutes). A crashed/closed client
# stops the heart-beat, so its session goes stale after the lease and no longer
# blocks a fresh login - preventing a permanent lockout.
_SESSION_LEASE_MINUTES = int(os.getenv("UNINEX_SESSION_LEASE_MINUTES", "5"))
_SETUP_USERNAME = os.getenv("UNINEX_SETUP_USERNAME", "setupdeploy")
_SETUP_PASSWORD = os.getenv("UNINEX_SETUP_PASSWORD", "")
_SETUP_ALLOWED_PATHS = [
    "/api/tenants",
    "/api/stores",
    "/api/stores/tenant/{tenant_id}",
    "/api/stores/{store_id}/agent-config",
]

@router.post("/login")
def login(req: LoginRequest, request: Request):
    if req.username.strip().lower() == _SETUP_USERNAME.lower():
        record_audit(
            ctx=request,
            action="auth.login.denied",
            category="auth",
            target_type="user",
            target_id=req.username,
            target_label=req.username,
            status=AuditStatus.FAILURE,
            error_message="Setup deploy user is restricted to setup provisioning only",
            reason=f"Rejected login for setup deploy user '{req.username}' on standard auth endpoint",
            actor_override={"actor_name": req.username, "actor_email": req.username},
        )
        raise HTTPException(status_code=403, detail="Setup deploy user is restricted to setup provisioning only")

    user = AuthService().login(req.username, req.password)

    if not user:
        record_audit(
            ctx=request,
            action="auth.login.failure",
            category="auth",
            target_type="user",
            target_id=req.username,
            target_label=req.username,
            status=AuditStatus.FAILURE,
            error_message="Invalid username or password",
            reason=f"Failed login attempt for username '{req.username}'",
            actor_override={"actor_name": req.username, "actor_email": req.username},
        )
        raise HTTPException(status_code=401, detail="Invalid Username Or Password")

    # Single active session: block this login if the user is already signed in
    # (and still active) on another system.
    repo = UserRepository()
    if repo.is_session_active(user["user_id"], _SESSION_LEASE_MINUTES):
        record_audit(
            ctx=request,
            action="auth.login.denied",
            category="auth",
            target_type="user",
            target_id=user["user_id"],
            target_label=user["username"],
            status=AuditStatus.FAILURE,
            error_message="User already has an active session on another system",
            reason=f"Blocked concurrent login for '{user['username']}' (single-session policy)",
            actor_override={"actor_name": user["username"], "actor_email": user.get("username")},
        )
        raise HTTPException(
            status_code=409,
            detail="This user is already signed in on another system. Sign out there first, or try again in a few minutes.",
        )

    primary_role = user["roles"][0] if user["roles"] else {}
    role_names = [r["role_name"] for r in user["roles"]]
    actor_role = ActorRole.ADMIN if user.get("is_platform_user") or any(r in {"SUPER_ADMIN", "PLATFORM_OWNER"} for r in role_names) else ActorRole.CUSTOMER

    # STRICT AUDIT: Log success before token credential is minted and returned
    record_audit_strict(
        ctx=request,
        action="auth.login.success",
        category="auth",
        target_type="user",
        target_id=user["user_id"],
        target_label=user["username"],
        reason=f"User '{user['username']}' authenticated successfully",
        metadata={
            "tenant_id": user.get("tenant_id"),
            "is_platform_user": user.get("is_platform_user"),
            "roles": role_names,
        },
        actor_override={
            "actor_id": user["user_id"],
            "actor_role": actor_role,
            "actor_email": user.get("username"),
            "actor_name": user.get("first_name") or user.get("username"),
        },
    )

    # Claim this session (newest login owns it) and stamp the token with its id
    # so every subsequent request can be validated against the active session.
    session_id = str(uuid.uuid4())
    repo.set_active_session(user["user_id"], session_id)

    token = create_access_token({
        "sub": user["user_id"],
        "username": user["username"],
        "tenant_id": user["tenant_id"],
        "is_platform_user": user["is_platform_user"],
        "role_names": role_names,
        "store_id": primary_role.get("store_id"),
        "store_code": primary_role.get("store_code"),
        "sid": session_id,
    })

    return {"token": token, "token_type": "bearer", "user": user}


@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    """Release the active session immediately on explicit sign-out so the user
    can sign in elsewhere without waiting for the lease to lapse. Only clears
    the session this token owns (sid-guarded)."""
    UserRepository().clear_active_session(current_user.get("sub"), current_user.get("sid"))
    return {"ok": True}


@router.post("/setup-login")
def setup_login(req: LoginRequest, request: Request, x_nexora_setup_checksum: str | None = Header(default=None)):
    if not _SETUP_PASSWORD:
        raise HTTPException(status_code=503, detail="Setup provisioning access is not configured on this HO")
    if req.username.strip().lower() != _SETUP_USERNAME.lower():
        record_audit(
            ctx=request,
            action="auth.setup_login.failure",
            category="auth",
            target_type="setup_account",
            target_id=req.username,
            target_label=req.username,
            status=AuditStatus.FAILURE,
            error_message="Invalid setup credentials",
            reason=f"Failed setup login attempt for username '{req.username}'",
            actor_override={"actor_name": req.username, "actor_email": req.username},
        )
        raise HTTPException(status_code=401, detail="Invalid setup credentials")

    expected_checksum = setup_access_checksum(
        _SETUP_USERNAME,
        _SETUP_PASSWORD,
        allowed_paths=_SETUP_ALLOWED_PATHS,
    )
    if not x_nexora_setup_checksum or x_nexora_setup_checksum != expected_checksum:
        record_audit(
            ctx=request,
            action="auth.setup_login.failure",
            category="auth",
            target_type="setup_account",
            target_id=req.username,
            target_label=req.username,
            status=AuditStatus.FAILURE,
            error_message="Invalid setup checksum",
            reason="Setup login rejected due to invalid security checksum",
            actor_override={"actor_name": req.username, "actor_email": req.username},
        )
        raise HTTPException(status_code=401, detail="Invalid setup checksum")

    user = AuthService().login(req.username, req.password)
    if not user:
        record_audit(
            ctx=request,
            action="auth.setup_login.failure",
            category="auth",
            target_type="setup_account",
            target_id=req.username,
            target_label=req.username,
            status=AuditStatus.FAILURE,
            error_message="Invalid setup credentials",
            reason="Setup provisioning authentication failed in database",
            actor_override={"actor_name": req.username, "actor_email": req.username},
        )
        raise HTTPException(status_code=401, detail="Invalid setup credentials")

    # STRICT AUDIT: Log success before setup token credential is issued
    record_audit_strict(
        ctx=request,
        action="auth.setup_login.success",
        category="auth",
        target_type="setup_session",
        target_id=user["user_id"],
        target_label=user["username"],
        reason="Store agent setup provisioning token minted",
        metadata={
            "scope": "setup_readonly",
            "allowed_paths": _SETUP_ALLOWED_PATHS,
        },
        actor_override={
            "actor_id": user["user_id"],
            "actor_role": ActorRole.ADMIN,
            "actor_email": user["username"],
            "actor_name": user.get("first_name") or user["username"],
        },
    )

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
