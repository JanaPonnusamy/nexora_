from __future__ import annotations

"""License activation: trial-to-licensed state for tenants sold to under a
demo-first sales motion.

Two routers, same split as modules.agent_ops:
  * ``agent_router`` (prefix ``/agent/license``) is what the unattended store
    agent calls on its normal heartbeat cadence. It sits under ``/agent/*``,
    which the auth middleware in api/app.py never gates - there is no
    user/JWT on a store machine.
  * ``router`` (prefix ``/api/licensing``) is the HO-only admin surface for
    issuing/revoking/renewing keys and choosing a tenant's DB mode. Locked to
    super admins via require_super_admin - licensing is an HO business
    concern, not something any tenant-scoped login should reach.

Terminology note: "activate"/"activation" already means something else in
this codebase (modules.desktop_client - approving a physical PC to run the
client). This module intentionally uses license_key / license_state instead.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from dependencies.store_scope import require_super_admin
from modules.licensing import service
from modules.licensing.schemas import (
    CheckinRequest,
    IssueKeyRequest,
    RenewRequest,
    RevokeRequest,
    SetDbModeRequest,
)

agent_router = APIRouter(prefix="/agent/license", tags=["Agent License"])
router = APIRouter(
    prefix="/api/licensing",
    tags=["Licensing"],
    dependencies=[Depends(require_super_admin)],
)


@agent_router.post("/checkin")
def checkin(payload: CheckinRequest):
    return service.checkin(payload.store_id, payload.agent_version)


@router.get("/tenants")
def list_tenants(tenant_id: Optional[str] = None):
    return service.list_tenants(tenant_id)


@router.get("/tenants/{tenant_id}")
def get_tenant(tenant_id: str):
    return service.get_tenant_license(tenant_id)


@router.post("/tenants/{tenant_id}/issue-key")
def issue_key(tenant_id: str, payload: IssueKeyRequest, current_user: dict = Depends(require_super_admin)):
    issued_by = current_user.get("email") or current_user.get("username") or "HO_ADMIN"
    return service.issue_key(tenant_id, payload.license_key, issued_by, payload.expires_at, payload.notes)


@router.post("/tenants/{tenant_id}/revoke")
def revoke(tenant_id: str, payload: RevokeRequest, current_user: dict = Depends(require_super_admin)):
    revoked_by = current_user.get("email") or current_user.get("username") or "HO_ADMIN"
    return service.revoke(tenant_id, revoked_by, payload.notes)


@router.post("/tenants/{tenant_id}/renew")
def renew(tenant_id: str, payload: RenewRequest, current_user: dict = Depends(require_super_admin)):
    issued_by = current_user.get("email") or current_user.get("username") or "HO_ADMIN"
    return service.renew(tenant_id, payload.expires_at, issued_by)


@router.put("/tenants/{tenant_id}/db-mode")
def set_db_mode(tenant_id: str, payload: SetDbModeRequest):
    return service.set_db_mode(
        tenant_id, payload.mode, payload.server, payload.database,
        payload.username, payload.password, payload.driver,
    )
