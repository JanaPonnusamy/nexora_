"""Non-Moving Report API — read-only dwell-days non-moving stock over sync.*.

tenant-scoped; a single store may be chosen (else all stores of the tenant).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.nonmoving_report import service

router = APIRouter(prefix="/api/non-moving-report", tags=["Non-Moving Report"])


@router.get("/data")
def data(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    basis: str = Query("sold", description="sold (last-sold) | received (last-received)"),
    min_days: int = Query(90, ge=0),
    max_days: Optional[int] = Query(None, ge=0),
    include_nil: bool = Query(False),
    supplier_code: Optional[str] = Query(None),
    supplier_mode: int = Query(0, description="0=product supplier, 1=batch supplier"),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.data(tenant_id, store_id, basis, min_days, max_days,
                        include_nil, supplier_code, supplier_mode)


@router.get("/suppliers")
def suppliers(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    supplier_mode: int = Query(0),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.suppliers(tenant_id, store_id, supplier_mode)
