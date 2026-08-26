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


@router.get("/date-bounds")
def date_bounds(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    supplier_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.date_bounds(tenant_id, store_id, supplier_code)


@router.get("/suppliers")
def suppliers(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.suppliers(tenant_id, store_id)


@router.get("/data")
def data(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    status: str = Query("all"),
    group_by: str = Query("summary"),
    supplier_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.expiry_data(tenant_id, store_id, from_date, to_date, status,
                               group_by, supplier_code)


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


@router.get("/pending-months")
def pending_months(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("pending-months", tenant_id, store_id)


@router.get("/pending-by-month")
def pending_by_month(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    month: str = Query(..., description="yyyy-MM"),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.run("pending-by-month", tenant_id, store_id, None, None, month)


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
