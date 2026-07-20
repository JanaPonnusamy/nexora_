from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

from modules.procurement.reports.excel_exporter import ExcelExporter
from modules.procurement.reports.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Procurement Reports"])

report_service = ReportService()


@router.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.get("/dashboard")
def dashboard(
    tenant_id: str = Query(...),
    from_month: str = Query(...),
    to_month: str = Query(...),
):
    return report_service.dashboard(tenant_id, from_month, to_month)


@router.get("/store-analysis")
def store_analysis(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    from_month: Optional[str] = Query(None),
    to_month: Optional[str] = Query(None),
):
    if not from_month or not to_month:
        now = datetime.now()
        to_month = f"{now.year}-{str(now.month).zfill(2)}"
        from_month = f"{now.year - 1}-{str(now.month).zfill(2)}"
    return report_service.store_analysis(tenant_id, store_id, from_month, to_month)


@router.get("/compare")
def compare(
    tenant_id: str = Query(...),
    month_a: str = Query(...),
    month_b: str = Query(...),
):
    return report_service.compare(tenant_id, month_a, month_b)


@router.get("/compare/export.xlsx")
def compare_excel(
    tenant_id: str = Query(...),
    month_a: str = Query(...),
    month_b: str = Query(...),
):
    payload = report_service.compare(tenant_id, month_a, month_b)
    content = ExcelExporter.build_workbook(payload["stores"], "Month Compare")
    filename = f"Month_Compare_{month_a}_vs_{month_b}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard/export.xlsx")
def dashboard_excel(
    tenant_id: str = Query(...),
    from_month: str = Query(...),
    to_month: str = Query(...),
):
    payload = report_service.dashboard(tenant_id, from_month, to_month)
    content = ExcelExporter.build_workbook(payload["stores"], "Store Summary")
    filename = f"All_Store_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/store-analysis/export.xlsx")
def store_analysis_excel(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    from_month: str = Query(...),
    to_month: str = Query(...),
):
    payload = report_service.store_analysis(tenant_id, store_id, from_month, to_month)
    content = ExcelExporter.build_workbook(payload["rows"], "Monthly Analysis")
    filename = (
        f"{payload['store_code']}_Monthly_Analysis_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
