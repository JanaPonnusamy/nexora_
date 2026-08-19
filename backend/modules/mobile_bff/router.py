from __future__ import annotations

"""Mobile BFF endpoints, mounted at /api/mobile/v1.

Additive only: no existing router, service or repository is modified, so the
web console and Electron desktop client are unaffected by anything here.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.audit.models import ActorRole, AuditStatus
from modules.audit.writer import record_audit, record_audit_strict

# Read-only reuse of the supplier module's own query. Nothing there is
# modified; see the /suppliers endpoint for why its router cannot be used.
from modules.supplier_stock_analysis import service as supplier_service
from services.auth_service import AuthService

from . import dashboard as dashboard_builder
from . import repository, service
from .schemas import (
    DashboardResponse,
    HandshakeResponse,
    LogoutRequest,
    MobileLoginRequest,
    RefreshRequest,
    TokenPair,
)

router = APIRouter(prefix="/api/mobile/v1", tags=["Mobile BFF"])


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/handshake", response_model=HandshakeResponse)
def handshake(response: Response):
    """Public. Lets a build check compatibility before showing a login form."""
    response.headers["X-API-Version"] = service.API_VERSION
    return service.handshake()


@router.post("/auth/login", response_model=TokenPair)
def login(req: MobileLoginRequest, request: Request):
    """Public. Same credentials as /api/auth/login, but also returns a refresh
    token so the session survives past the 12-hour access-token lifetime."""
    result = service.login(
        req.username, req.password, req.device, ip=_client_ip(request)
    )

    if not result:
        record_audit(
            ctx=request,
            action="mobile.login.failure",
            category="auth",
            target_type="user",
            target_id=req.username,
            target_label=req.username,
            status=AuditStatus.FAILURE,
            error_message="Invalid username or password",
            reason=f"Failed mobile login for '{req.username}'",
            metadata={"device_id": req.device.device_id},
            actor_override={"actor_name": req.username, "actor_email": req.username},
        )
        raise HTTPException(status_code=401, detail="Invalid Username Or Password")

    user = result["user"]
    role_names = [r["role_name"] for r in (user.get("roles") or [])]
    actor_role = (
        ActorRole.ADMIN
        if user.get("is_platform_user")
        or any(r in {"SUPER_ADMIN", "PLATFORM_OWNER"} for r in role_names)
        else ActorRole.CUSTOMER
    )

    # Strict: the audit row must be durable before credentials are returned,
    # matching auth_controller.login.
    record_audit_strict(
        ctx=request,
        action="mobile.login.success",
        category="auth",
        target_type="user",
        target_id=user["user_id"],
        target_label=user["username"],
        reason=f"User '{user['username']}' signed in from mobile",
        metadata={
            "device_id": req.device.device_id,
            "platform": req.device.platform,
            "app_version": req.device.app_version,
            "roles": role_names,
        },
        actor_override={
            "actor_id": user["user_id"],
            "actor_role": actor_role,
            "actor_email": user.get("username"),
            "actor_name": user.get("first_name") or user.get("username"),
        },
    )
    return result


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(req: RefreshRequest, request: Request):
    """Public — authenticated by the refresh token itself, not a bearer JWT
    (the access token is expired by the time this is called)."""
    try:
        return service.refresh(
            req.refresh_token, req.device_id, ip=_client_ip(request)
        )
    except service.SessionError as exc:
        # Reuse means a token was replayed; the whole device chain has been
        # revoked. Audited as a failure so it is visible in the audit trail.
        record_audit(
            ctx=request,
            action="mobile.refresh.reuse_detected"
            if exc.reuse_detected
            else "mobile.refresh.failure",
            category="auth",
            target_type="refresh_token",
            target_id=req.device_id,
            target_label=req.device_id,
            status=AuditStatus.FAILURE,
            error_message=exc.message,
            reason="Mobile refresh token rejected",
            metadata={"device_id": req.device_id, "reuse": exc.reuse_detected},
        )
        raise HTTPException(status_code=401, detail=exc.message)


@router.post("/auth/logout")
def logout(
    req: LogoutRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Revokes the refresh chain. The access token stays valid until it expires
    — it is stateless and this codebase has no denylist — so clients must also
    discard it locally."""
    revoked = service.logout(
        user_id=current_user["sub"],
        raw_token=req.refresh_token,
        device_id=req.device_id,
        all_devices=req.all_devices,
    )
    record_audit(
        ctx=request,
        action="mobile.logout",
        category="auth",
        target_type="user",
        target_id=current_user["sub"],
        target_label=current_user.get("username"),
        reason="Mobile session ended",
        metadata={
            "device_id": req.device_id,
            "all_devices": req.all_devices,
            "tokens_revoked": revoked,
        },
    )
    return {"revoked": revoked}


@router.get("/auth/devices")
def devices(current_user: dict = Depends(get_current_user)):
    """Live mobile sessions for the caller."""
    return {"devices": repository.list_devices(current_user["sub"])}


@router.get("/suppliers")
def suppliers(
    search: str = Query(default="", max_length=200),
    store_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Supplier list for the mobile Supplier screen.

    This exists because `/api/supplier-stock-analysis/suppliers` is behind
    `require_admin_role`, which 403s any login whose roles are all purchase
    manager and/or salesman — precisely the field roles this app is built for.
    Those users were getting an empty supplier list with no explanation.

    What is deliberately *not* copied over from that module: supplier products,
    stock, matching, reports and the cross-store dashboards. Those are the
    admin planning tools the gate was written for, and they stay gated. This
    endpoint exposes the supplier list alone.

    Scope comes from the token, never from a query parameter, so a client
    cannot widen it. `assert_tenant_access` still applies — the tenant is the
    boundary this codebase enforces (see dependencies/store_scope.py).
    """
    user = AuthService().get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Not Found")

    tenant_id = user.get("tenant_id") or current_user.get("tenant_id")
    if not tenant_id:
        # A platform user has no tenant of their own, so there is no supplier
        # list to resolve without one. Say so rather than returning every
        # tenant's suppliers.
        raise HTTPException(
            status_code=400,
            detail="This account is not scoped to a tenant, so it has no supplier list.",
        )
    assert_tenant_access(current_user, tenant_id)

    # Falls back to the store baked into the token, matching /dashboard.
    effective_store = store_id or current_user.get("store_id")
    return supplier_service.list_suppliers(tenant_id, effective_store, search)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    store_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Single aggregate for the Home tab.

    Unlike the rest of the API, tenant_id is taken from the token rather than a
    query parameter — the mobile client should not have to carry scoping on
    every call, and it must not be able to widen its own scope.
    """
    user = AuthService().get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Not Found")

    if user.get("tenant_id"):
        assert_tenant_access(current_user, user["tenant_id"])

    # Fall back to the store baked into the token when the client sends none.
    effective_store = store_id or current_user.get("store_id")
    return dashboard_builder.build(user, effective_store)
