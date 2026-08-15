from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from services.store_service import StoreService
from dtos.store_request import StoreRequest, StoreStatusRequest
from dependencies.auth import get_current_user_optional, get_current_user
from dependencies.store_scope import has_unrestricted_scope
from modules.audit.writer import record_audit
from modules.audit.diff import compute_mutation_diff
from modules.audit.context import AuditContext

router = APIRouter(
    prefix="/api/stores",
    tags=["Stores"]
)

def _serialize(r):
    return {
        "store_id": str(r[0]),
        "tenant_id": str(r[1]),
        "store_code": r[2],
        "store_name": r[3],
        "server_name": r[4],
        "database_name": r[5],
        "is_active": bool(r[6]),
    }

@router.get("")
def get_stores(current_user: dict | None = Depends(get_current_user_optional)):

    rows = StoreService().get_all()

    stores = [
        {
            "store_id": str(r[0]),
            "tenant_id": str(r[1]),
            "store_code": r[2],
            "store_name": r[3],
            "server_name": r[4],
            "database_name": r[5],
            "is_active": bool(r[6])
        }
        for r in rows
    ]

    if has_unrestricted_scope(current_user):
        return stores

    # Non-broad users (purchase manager, salesman, any tenant-scoped role) only
    # see their own tenant's stores - Stock Availability is a network-wide
    # stock lookup, so any store within their own tenant is fair game, just
    # never another tenant's. Previously every store across every tenant was
    # returned to any authenticated user.
    own_tenant_id = str(current_user.get("tenant_id") or "")
    return [s for s in stores if s["tenant_id"] == own_tenant_id]


@router.get("/tenant/{tenant_id}")
def get_by_tenant(tenant_id: str, current_user: dict | None = Depends(get_current_user_optional)):

    if not has_unrestricted_scope(current_user) and str(current_user.get("tenant_id") or "") != str(tenant_id):
        raise HTTPException(status_code=403, detail="You do not have access to this tenant.")

    rows = StoreService().get_by_tenant(
        tenant_id
    )

    stores = [
        {
            "store_id": str(r[0]),
            "store_code": r[2],
            "store_name": r[3]
        }
        for r in rows
    ]

    # The tenant check above already rejected any tenant_id that isn't this
    # user's own (or let a super admin/platform user through), so every
    # store this query returns is already in-scope.
    return stores


@router.get("/{store_id}/agent-config")
def get_agent_config(store_id: str):

    row = StoreService().get_agent_config(
        store_id
    )

    if not row:
        return {
            "error": "Store Not Found"
        }

    return {
        "store_id": str(row[0]),
        "store_code": row[1],
        "server_name": row[2],
        "database_name": row[3],
        "username": row[4],
        "password_encrypted":
            row[5].hex()
            if row[5]
            else None,
        "connection_type": row[6],
        "agent_version": row[7],
        "is_active": bool(row[8])
    }


@router.get("/{store_id}")
def get_store(store_id: str):

    r = StoreService().get_by_id(store_id)

    if not r:
        return {
            "error": "Store Not Found"
        }

    return {
        "store_id": str(r[0]),
        "tenant_id": str(r[1]),
        "store_code": r[2],
        "store_name": r[3],
        "server_name": r[4],
        "database_name": r[5],
        "is_active": bool(r[6])
    }


@router.post("", status_code=201)
def create_store(body: StoreRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = StoreService()
    store_code = body.store_code.strip()
    store_name = body.store_name.strip()
    if not body.tenant_id.strip():
        raise HTTPException(status_code=400, detail="Tenant is required")
    if not store_code:
        raise HTTPException(status_code=400, detail="Store code is required")
    if not store_name:
        raise HTTPException(status_code=400, detail="Store name is required")
    if svc.store_code_exists(store_code, body.tenant_id):
        raise HTTPException(status_code=400, detail="Store code already exists for this tenant")
    new_id = svc.create(body.tenant_id, store_code, store_name, body.server_name, body.database_name)
    r = svc.get_by_id(str(new_id))
    serialized = _serialize(r)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="store.create",
        target_type="store",
        target_id=str(new_id),
        target_label=f"{store_name} ({store_code})",
        reason=f"Created store '{store_name}' ({store_code})",
        metadata=serialized,
    )
    return serialized


@router.put("/{store_id}")
def update_store(store_id: str, body: StoreRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = StoreService()
    store_code = body.store_code.strip()
    store_name = body.store_name.strip()
    if not store_code:
        raise HTTPException(status_code=400, detail="Store code is required")
    if not store_name:
        raise HTTPException(status_code=400, detail="Store name is required")
    existing = svc.get_by_id(store_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Store Not Found")
    if svc.store_code_exists(store_code, body.tenant_id, store_id):
        raise HTTPException(status_code=400, detail="Store code already exists for this tenant")

    before = _serialize(existing)
    svc.update(store_id, body.tenant_id, store_code, store_name, body.server_name, body.database_name)
    r = svc.get_by_id(store_id)
    after = _serialize(r)

    changed_fields, diff_details = compute_mutation_diff(
        before,
        {"store_code": store_code, "store_name": store_name, "server_name": body.server_name, "database_name": body.database_name},
    )
    changed_str = ", ".join(changed_fields) if changed_fields else "no field changes"

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="store.update",
        target_type="store",
        target_id=store_id,
        target_label=f"{store_name} ({store_code})",
        reason=f"Updated store '{store_name}' (changed: {changed_str})",
        metadata={"diff": diff_details, "changed_fields": changed_fields},
    )
    return after


@router.patch("/{store_id}/status")
def set_store_status(store_id: str, body: StoreStatusRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = StoreService()
    existing = svc.get_by_id(store_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Store Not Found")
    before = _serialize(existing)
    svc.set_active(store_id, body.is_active)
    r = svc.get_by_id(store_id)
    after = _serialize(r)

    verb = "Activated" if body.is_active else "Deactivated"
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="store.status.update",
        target_type="store",
        target_id=store_id,
        target_label=before["store_name"],
        reason=f"{verb} store '{before['store_name']}'",
        metadata={"is_active": body.is_active},
    )
    return after