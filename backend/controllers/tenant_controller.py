
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from services.tenant_service import TenantService
from dtos.tenant_request import TenantRequest, TenantStatusRequest
from dependencies.auth import get_current_user_optional
from dependencies.store_scope import has_unrestricted_scope

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
    own_tenant_id = str(current_user.get("tenant_id") or "")
    return [t for t in tenants if t["tenant_id"] == own_tenant_id]

@router.get("/{tenant_id}")
def get_tenant(tenant_id: str):
    r = TenantService().get_by_id(tenant_id)
    if not r:
        raise HTTPException(status_code=404, detail="Tenant Not Found")
    return _serialize(r)

@router.post("", status_code=201)
def create_tenant(body: TenantRequest):
    new_id = TenantService().create(
        body.tenant_code, body.tenant_abbreviation, body.tenant_name, body.db_name
    )
    r = TenantService().get_by_id(str(new_id))
    return _serialize(r)

@router.put("/{tenant_id}")
def update_tenant(tenant_id: str, body: TenantRequest):
    TenantService().update(
        tenant_id, body.tenant_code, body.tenant_abbreviation, body.tenant_name, body.db_name
    )
    r = TenantService().get_by_id(tenant_id)
    if not r:
        raise HTTPException(status_code=404, detail="Tenant Not Found")
    return _serialize(r)

@router.patch("/{tenant_id}/status")
def set_tenant_status(tenant_id: str, body: TenantStatusRequest):
    TenantService().set_active(tenant_id, body.is_active)
    r = TenantService().get_by_id(tenant_id)
    if not r:
        raise HTTPException(status_code=404, detail="Tenant Not Found")
    return _serialize(r)
