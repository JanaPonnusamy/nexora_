"""Expiry Report API — read-only supplier-expiry drill-down over sync.* data.

tenant -> store summary -> supplier summary -> ( pending details |
          ack-wise -> ack product details ). Every level is tenant-scoped;
store-level calls additionally require store_id (checked via store_scope).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.expiry_report import service

router = APIRouter(prefix="/api/expiry-report", tags=["Expiry Report"])


@router.get("/store-summary")
def store_summary(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("store-summary", tenant_id)


@router.get("/supplier-summary")
def supplier_summary(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("supplier-summary", tenant_id, store_id)


@router.get("/supplier-pending")
def supplier_pending(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    supplier_code: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("supplier-pending", tenant_id, store_id, supplier_code)


@router.get("/supplier-acks")
def supplier_acks(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    supplier_code: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("supplier-acks", tenant_id, store_id, supplier_code)


@router.get("/ack-products")
def ack_products(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    ack_number: str = Query(...),
    supplier_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("ack-products", tenant_id, store_id, None, ack_number)
