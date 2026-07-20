"""Reports API — read-only store reports over the synced `sync.*` data.

Ported from the legacy WinForms Reports module. Every report is scoped by a
single tenant + store and (where applicable) a date range. No writes.
"""

from typing import Optional

from fastapi import APIRouter, Query

from modules.reports import service
from modules.reports.schemas import ReportResult

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("")
def list_reports():
    """Catalog of available reports + which inputs each one needs."""
    return service.catalog()


@router.get("/suppliers")
def report_suppliers(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    q: str = Query("", alias="q"),
    limit: int = Query(30, ge=1, le=100),
):
    """Supplier lookup for the Non-Moving / Purchased-Not-Sold filters."""
    return service.suppliers(tenant_id, store_id, q, limit)


@router.get("/non-moving/highlights", response_model=ReportResult)
def non_moving_highlights(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    dwell_days: int = Query(120),
    min_pur_age: int = Query(10),
    limit: int = Query(50, ge=1, le=200),
):
    """Lean, TOP-N variant of the Non Moving report for rotating highlight panels."""
    return service.non_moving_highlights(tenant_id, store_id, dwell_days, min_pur_age, limit)


@router.get("/{report_key}", response_model=ReportResult)
def run_report(
    report_key: str,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    dwell_days: Optional[int] = Query(None),
    supplier_code: Optional[str] = Query(None),
    division_code: Optional[str] = Query(None),
):
    return service.run(
        report_key, tenant_id, store_id, from_date, to_date,
        dwell_days, supplier_code, division_code,
    )
