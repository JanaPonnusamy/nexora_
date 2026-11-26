"""Stock Check Report API — read-only sublocation-range physical count sheet.

Ported from the legacy VB6 OrderRpt app. View-only: no insert/update/delete
endpoints. Reads sync.Batches / sync.Products (NEXORA_PLATFORM); the caller
is expected to trigger a sync for the store first via /api/sync/tasks/create.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.stock_check_report import service
from modules.stock_check_report.schemas import StockCheckQuery, StockCheckResult

router = APIRouter(prefix="/api/stock-check-report", tags=["Stock Check Report"])


@router.get("/rows", response_model=StockCheckResult)
def get_rows(
    tenant_id: str,
    store_id: str,
    sublocation_from: str = "",
    sublocation_to: str = "",
    product_code_from: Optional[int] = None,
    product_code_to: Optional[int] = None,
    product_name: str = "",
    supplier_code: str = "",
    unit_description: str = "",
    batch_code: str = "",
    expiry_from: str = "",
    expiry_to: str = "",
    min_stock: Optional[float] = None,
    max_stock: Optional[float] = None,
    include_zero_stock: bool = False,
    include_negative_stock: bool = False,
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    query = StockCheckQuery(
        sublocation_from=sublocation_from,
        sublocation_to=sublocation_to,
        product_code_from=product_code_from,
        product_code_to=product_code_to,
        product_name=product_name,
        supplier_code=supplier_code,
        unit_description=unit_description,
        batch_code=batch_code,
        expiry_from=expiry_from,
        expiry_to=expiry_to,
        min_stock=min_stock,
        max_stock=max_stock,
        include_zero_stock=include_zero_stock,
        include_negative_stock=include_negative_stock,
    )
    return service.get_stock_check_report(tenant_id, store_id, query)


@router.get("/sublocations")
def search_sublocations(tenant_id: str, store_id: str, q: str = "", current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    return {"sublocations": service.search_sublocations(tenant_id, store_id, q)}


@router.get("/suppliers")
def list_suppliers(tenant_id: str, store_id: str, current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    return {"suppliers": service.list_suppliers(tenant_id, store_id)}


@router.get("/units")
def list_units(tenant_id: str, store_id: str, current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    return {"units": service.list_units(tenant_id, store_id)}
