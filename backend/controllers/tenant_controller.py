
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from services.tenant_service import TenantService
from dtos.tenant_request import TenantRequest, TenantStatusRequest
from dependencies.auth import get_current_user_optional, get_current_user
from dependencies.store_scope import has_unrestricted_scope
from modules.audit.writer import record_audit
from modules.audit.diff import compute_mutation_diff
from modules.audit.context import AuditContext

router = APIRouter(prefix="/api/tenants", tags=["Tenants"])

def _serialize(r):
    return {
        "tenant_id": str(r[0]),
        "tenant_code": r[1],
        "tenant_abbreviation": r[2],
        "tenant_name": r[3],
        "db_name": r[4],
        "is_active": bool(r[5]),
    }

@router.get("")
def get_tenants(current_user: dict | None = Depends(get_current_user_optional)):
    rows = TenantService().get_all()
    tenants = [_serialize(r) for r in rows]
    if has_unrestricted_scope(current_user):
        return tenants
    # Non-broad users (including purchase/salesman) only see their own tenant -
    # otherwise every tenant name/id was exposed to any authenticated user.
    own_tenant_id = str(current_user.get("tenant_id") or "") if current_user else ""
    return [t for t in tenants if t["tenant_id"] == own_tenant_id]

@router.get("/{tenant_id}")
def get_tenant(tenant_id: str):
    r = TenantService().get_by_id(tenant_id)
    if not r:
        raise HTTPException(status_code=404, detail="Tenant Not Found")
    return _serialize(r)

@router.post("", status_code=201)
def create_tenant(body: TenantRequest, request: Request, current_user: dict = Depends(get_current_user)):
    new_id = TenantService().create(
        body.tenant_code, body.tenant_abbreviation, body.tenant_name, body.db_name
    )
    r = TenantService().get_by_id(str(new_id))
    serialized = _serialize(r)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="tenant.create",
        target_type="tenant",
        target_id=str(new_id),
        target_label=body.tenant_name,
        reason=f"Created tenant '{body.tenant_name}' ({body.tenant_code})",
        metadata=serialized,
    )
    return serialized

@router.put("/{tenant_id}")
def update_tenant(tenant_id: str, body: TenantRequest, request: Request, current_user: dict = Depends(get_current_user)):
    existing = TenantService().get_by_id(tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Tenant Not Found")
    before = _serialize(existing)

    TenantService().update(
        tenant_id, body.tenant_code, body.tenant_abbreviation, body.tenant_name, body.db_name
    )
    r = TenantService().get_by_id(tenant_id)
    after = _serialize(r)

    changed_fields, diff_details = compute_mutation_diff(
        before,
        {"tenant_code": body.tenant_code, "tenant_abbreviation": body.tenant_abbreviation, "tenant_name": body.tenant_name, "db_name": body.db_name},
    )
    changed_str = ", ".join(changed_fields) if changed_fields else "no field changes"

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="tenant.update",
        target_type="tenant",
        target_id=tenant_id,
        target_label=body.tenant_name,
        reason=f"Updated tenant '{body.tenant_name}' (changed: {changed_str})",
        metadata={"diff": diff_details, "changed_fields": changed_fields},
    )
    return after

@router.patch("/{tenant_id}/status")
def set_tenant_status(tenant_id: str, body: TenantStatusRequest, request: Request, current_user: dict = Depends(get_current_user)):
    existing = TenantService().get_by_id(tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Tenant Not Found")
    before = _serialize(existing)

    TenantService().set_active(tenant_id, body.is_active)
    r = TenantService().get_by_id(tenant_id)
    after = _serialize(r)

    verb = "Activated" if body.is_active else "Deactivated"
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="tenant.status.update",
        target_type="tenant",
        target_id=tenant_id,
        target_label=before["tenant_name"],
        reason=f"{verb} tenant '{before['tenant_name']}'",
        metadata={"is_active": body.is_active},
    )
    return after
