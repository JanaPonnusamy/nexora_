"""Expiry Stock (Cutting Expiry) API — read-only on-hand near-expiry batch
listing over sync.* data. Tenant-scoped; store_id required."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.expiry_stock import service

router = APIRouter(prefix="/api/expiry-stock", tags=["Expiry Stock"])


@router.get("/date-bounds")
def date_bounds(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.date_bounds(tenant_id, store_id)


@router.get("/suppliers")
def suppliers(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.suppliers(tenant_id, store_id)


@router.get("/report")
def report(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    supplier_code: Optional[str] = Query(None),
    exp_from: Optional[str] = Query(None, alias="from"),
    exp_to: Optional[str] = Query(None, alias="to"),
    only_cutting: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.report(tenant_id, store_id, supplier_code, exp_from, exp_to,
                          only_cutting)
