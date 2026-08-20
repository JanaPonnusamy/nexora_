"""Stock Check Report API — read-only sublocation-range physical count sheet.

Ported from the legacy VB6 OrderRpt app. View-only: no insert/update/delete
endpoints. Reads sync.Batches / sync.Products (NEXORA_PLATFORM); the caller
is expected to trigger a sync for the store first via /api/sync/tasks/create.
"""

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.stock_check_report import service
from modules.stock_check_report.schemas import StockCheckResult

router = APIRouter(prefix="/api/stock-check-report", tags=["Stock Check Report"])


@router.get("/rows", response_model=StockCheckResult)
def get_rows(tenant_id: str, store_id: str, sublocation_from: str = "", sublocation_to: str = "", current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    return service.get_stock_check_report(tenant_id, store_id, sublocation_from, sublocation_to)


@router.get("/sublocations")
def search_sublocations(tenant_id: str, store_id: str, q: str = "", current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    return {"sublocations": service.search_sublocations(tenant_id, store_id, q)}
