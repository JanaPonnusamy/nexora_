"""Supplier Rate Engine API -- super admin only, cross-tenant.

Reads two tenants' real purchase data (SMS: OrderSMS on 192.168.10.32;
Nathan: NEXORA_PLATFORM sync.PurchaseTrans on 192.168.10.73) and computes,
for the same products (matched by normalised name), how much more one
tenant paid than the other actually paid -- monthwise/store-wise, a top-25
consolidated view, and bill-wise detail. Read-only: no endpoint here writes
to either tenant's database.
"""

import io
import re
from datetime import date, timedelta
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from dependencies.store_scope import require_super_admin
from modules.rate_analysis import excel
from modules.supplier_rate_engine import service

router = APIRouter(prefix="/api/supplier-rate-engine", tags=["Supplier Rate Engine"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(result: dict, name: str):
    safe = re.sub(r"[^A-Za-z0-9 _.-]", "_", name).strip()
    return Response(content=excel.build_workbook(result), media_type=_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{safe}_{date.today():%Y-%m-%d}.xlsx"'})


_BILL_COLS = [
    {"key": "bill_no", "label": "Bill No"},
    {"key": "grn_date", "label": "Date", "format": "date"},
    {"key": "store", "label": "Store"},
    {"key": "product_code", "label": "Code"},
    {"key": "product_name", "label": "Product", "width": 34},
    {"key": "qty", "label": "Qty", "format": "num1"},
    {"key": "actual_cost", "label": "Actual Cost", "format": "money"},
    {"key": "benchmark_cost", "label": "Benchmark Cost", "format": "money"},
    {"key": "loss", "label": "Loss", "format": "money"},
]

_MONTH_COLS = [
    {"key": "ym", "label": "Month"},
    {"key": "store", "label": "Store"},
    {"key": "qty", "label": "Qty", "format": "num1"},
    {"key": "loss", "label": "Loss", "format": "money"},
]

_PRODUCT_COLS = [
    {"key": "product_code", "label": "Code"},
    {"key": "product_name", "label": "Product", "width": 34},
    {"key": "total_loss", "label": "Total Loss", "format": "money"},
]


@router.get("/loss-report")
def loss_report(
    tenant: str = Query("SMS"),
    baseline: str = Query("nathan_actual", description="nathan_actual (only baseline live so far)"),
    year: int = Query(default_factory=lambda: date.today().year),
    format: str = "json",
    current_user: dict = Depends(require_super_admin),
):
    try:
        res = service.tenant_loss_report(tenant, baseline, year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if format.lower() != "xlsx":
        return res

    summary_rows = [{"store": k, "loss": v} for k, v in sorted(res["ytd_by_store"].items())]
    summary_cols = [{"key": "store", "label": "Store"}, {"key": "loss", "label": "YTD Loss", "format": "money"}]
    product_rows = [{"product_code": p["product_code"], "product_name": p["product_name"],
                      "total_loss": p["total_loss"]} for p in res["top_products"]]
    return _xlsx({
        "title": f"Supplier Rate Engine - {tenant} vs {baseline} - {year}",
        "notes": [f"YTD total loss: {res['ytd_total_loss']:,.2f}. Generated {res['generated_at']}.",
                  "Loss = (actual cost - benchmark cost) x qty, benchmark = median same-product cost "
                  "from the comparison tenant. Internal transfers (InvoiceSeries='TI') excluded.",
                  f"Cost-ratio outliers beyond {service.OUTLIER_RATIO_HIGH}x / below {service.OUTLIER_RATIO_LOW}x "
                  "excluded as likely pack-size mismatches."],
        "sheets": [
            {"name": "YTD by Store", "columns": summary_cols, "rows": summary_rows},
            {"name": "Top 25 Products", "columns": _PRODUCT_COLS, "rows": product_rows},
            {"name": "Monthwise", "columns": _MONTH_COLS, "rows": res["monthwise"]},
            {"name": "Bill-wise Detail", "columns": _BILL_COLS, "rows": res["bill_rows"]},
        ],
    }, f"SupplierRateEngine_{tenant}_{year}")


@router.get("/product/{product_name}/monthwise")
def product_monthwise(
    product_name: str,
    tenant: str = Query("SMS"),
    baseline: str = Query("nathan_actual"),
    year: int = Query(default_factory=lambda: date.today().year),
    current_user: dict = Depends(require_super_admin),
):
    """Drill-down: one product's monthwise/store-wise loss breakdown, from
    the same top-25 consolidation (404s if it isn't in the top 25)."""
    res = service.tenant_loss_report(tenant, baseline, year)
    from modules.supplier_rate_engine import repository as repo
    key = repo.normalize_name(product_name)
    for p in res["top_products"]:
        if repo.normalize_name(p["product_name"]) == key:
            return p
    raise HTTPException(status_code=404, detail="Product not found in the top-25 consolidated loss list")


# --------------------------------------------------------------------------
# Reusable engine v2: upload reference list -> NMW variant picker -> select
# variants + tenant -> single-tenant report. No AI involved at any step.
# --------------------------------------------------------------------------

class VariantSelection(BaseModel):
    product_name: str
    mrp: Optional[float] = None
    sale_unit: Optional[str] = None
    purchase_unit: Optional[str] = None

    @field_validator("sale_unit", "purchase_unit", mode="before")
    @classmethod
    def _unit_to_str(cls, v):
        if v is None:
            return None
        return str(v)


class VarianceReportRequest(BaseModel):
    tenant: str  # "SMS" | "SUCCESS"
    variants: list[VariantSelection]
    days: int = 90
    format: str = "json"


def _read_reference_names(data: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    header = [str(c.value or "").strip().lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        col = header.index("product name") if "product name" in header else header.index("product")
    except ValueError:
        raise HTTPException(status_code=400, detail='Reference file needs a "Product Name" column')
    names = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if col < len(row) and row[col]:
            names.append(str(row[col]).strip())
    return names


@router.post("/variants/upload")
async def variants_upload(
    file: UploadFile = File(...),
    days: int = Query(90),
    current_user: dict = Depends(require_super_admin),
):
    """Step 1 of the engine: upload a reference product list, get back every
    NMW variant found per name (MRP/unit/sample cost) for manual review --
    nothing is auto-matched, per the NAN PRO false-match lesson."""
    names = _read_reference_names(await file.read())
    if not names:
        raise HTTPException(status_code=400, detail="No product names found in the uploaded file")
    period_end = date.today()
    period_start = period_end - timedelta(days=days)
    return {
        "window_days": days,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "results": service.nmw_variant_picker(names, period_start, period_end),
    }


@router.get("/nmw/activity-90d")
def nmw_activity_90d(
    days: int = Query(90),
    format: str = Query("json"),
    current_user: dict = Depends(require_super_admin),
):
    """NMW batch-wise purchase activity report: every real purchase line
    (cost, PTR, MRP, unit, supplier) for ANY product bought at NMW in the
    last `days` days, whether or not that product's current stock is zero --
    this reflects transactions, not a stock snapshot."""
    period_end = date.today()
    period_start = period_end - timedelta(days=days)
    from modules.supplier_rate_engine import repository as repo
    rows = repo.nmw_batch_activity(period_start, period_end)
    for r in rows:
        r["bill_no"] = r.pop("grn_number", None)
    # Split by (product name, MRP): a product billed under two different MRPs
    # is two distinct variants, never collapsed into one blanket rate -- same
    # rule as the NMW variant picker/benchmarks (OMEE CAP's 2 MRPs, etc.).
    product_totals = {}
    for r in rows:
        mrp = round(float(r["mrp"]), 2) if r["mrp"] is not None else None
        key = (repo.normalize_name(r["product_name"]), mrp)
        p = product_totals.setdefault(key, {
            "product_name": r["product_name"], "product_code": r["product_code"], "mrp": mrp,
            "lines": 0, "total_qty": 0.0, "min_cost": None, "max_cost": None, "min_ptr": None, "max_ptr": None,
            "sale_unit": r.get("sale_unit"), "purchase_unit": r.get("purchase_unit"),
        })
        p["lines"] += 1
        p["total_qty"] += float(r["qty"] or 0) + float(r["free_qty"] or 0)
        cost = float(r["item_cost"] or 0)
        if cost > 0:
            p["min_cost"] = cost if p["min_cost"] is None else min(p["min_cost"], cost)
            p["max_cost"] = cost if p["max_cost"] is None else max(p["max_cost"], cost)
        ptr = float(r["purchase_price"] or 0)
        if ptr > 0:
            p["min_ptr"] = ptr if p["min_ptr"] is None else min(p["min_ptr"], ptr)
            p["max_ptr"] = ptr if p["max_ptr"] is None else max(p["max_ptr"], ptr)
    product_rows = sorted(product_totals.values(), key=lambda p: (p["product_name"] or "", p["mrp"] or 0))

    result = {
        "title": f"NMW Purchase Activity - last {days} days (batch-wise)",
        "notes": [f"{period_start:%d-%b-%Y} to {period_end:%d-%b-%Y}. Every real NMW purchase line (InvoiceSeries='IV'; "
                  "internal transfers excluded), including products whose CURRENT stock is zero -- this reflects "
                  "transactions in the window, not today's stock snapshot.",
                  "Product Summary is split by (product name, MRP): a product billed under two different MRPs in "
                  "the window appears as two separate rows, each with its own cost/PTR range -- never blended."],
        "sheets": [
            {"name": "Product Summary", "columns": [
                {"key": "product_code", "label": "Code"}, {"key": "product_name", "label": "Product", "width": 34},
                {"key": "mrp", "label": "MRP", "format": "money"}, {"key": "sale_unit", "label": "Sale Unit"},
                {"key": "purchase_unit", "label": "Purchase Unit"}, {"key": "lines", "label": "Bill lines", "format": "int"},
                {"key": "total_qty", "label": "Total Qty", "format": "num1"},
                {"key": "min_cost", "label": "Min Cost", "format": "money"}, {"key": "max_cost", "label": "Max Cost", "format": "money"},
                {"key": "min_ptr", "label": "Min PTR", "format": "money"}, {"key": "max_ptr", "label": "Max PTR", "format": "money"},
            ], "rows": product_rows},
            {"name": "Batch-wise Detail", "columns": [
                {"key": "product_code", "label": "Code"}, {"key": "product_name", "label": "Product", "width": 34},
                {"key": "batch_code", "label": "Batch"}, {"key": "bill_no", "label": "Bill No"},
                {"key": "grn_date", "label": "Date", "format": "date"}, {"key": "qty", "label": "Qty", "format": "num1"},
                {"key": "free_qty", "label": "Free", "format": "num1"}, {"key": "item_cost", "label": "Cost", "format": "money"},
                {"key": "purchase_price", "label": "PTR", "format": "money"}, {"key": "mrp", "label": "MRP", "format": "money"},
                {"key": "sale_unit", "label": "Sale Unit"}, {"key": "purchase_unit", "label": "Purchase Unit"},
                {"key": "supplier_name", "label": "Supplier", "width": 28},
            ], "rows": rows},
        ],
    }
    if format.lower() != "xlsx":
        return result
    return _xlsx(result, f"NMW_Activity_{days}D")


@router.get("/products/suggest")
def products_suggest(
    q: str = Query(..., min_length=2),
    current_user: dict = Depends(require_super_admin),
):
    """Fast typeahead: distinct NMW product names matching the fragment, for
    the UI's live search dropdown (catalog-only, no cost lookup -- that
    happens for the names actually picked, via /variants/search)."""
    from modules.supplier_rate_engine import repository as repo
    return {"names": repo.nmw_product_name_suggest(q.strip())}


@router.get("/variants/search")
def variants_search(
    q: str = Query(..., min_length=2),
    days: int = Query(90),
    current_user: dict = Depends(require_super_admin),
):
    """Alternative to uploading a reference file: search NMW's own purchase
    history directly by a product-name fragment and get back the same
    variant-picker rows as the upload flow, for one name at a time. Lets the
    source list be built straight from NMW instead of an external Excel."""
    period_end = date.today()
    period_start = period_end - timedelta(days=days)
    return {
        "window_days": days,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "results": service.nmw_variant_picker([q.strip()], period_start, period_end),
    }


@router.post("/variance-report")
def variance_report(
    body: VarianceReportRequest,
    current_user: dict = Depends(require_super_admin),
):
    """Step 2: given the user's selected variant(s) and ONE tenant (SMS or
    Success -- never both in the same report), run the comparison against
    NMW's fixed low rate and return the result, or an Excel export."""
    period_end = date.today()
    period_start = period_end - timedelta(days=body.days)
    selected = [v.model_dump() for v in body.variants]
    try:
        res = service.store_tenant_variance_report(body.tenant, selected, period_start, period_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if body.format.lower() != "xlsx":
        return res

    bill_cols = [
        {"key": "bill_no", "label": "Bill No"},
        {"key": "batch_code", "label": "Batch"},
        {"key": "grn_date", "label": "Date", "format": "date"},
        {"key": "store", "label": "Store"},
        {"key": "product_code", "label": "Code"},
        {"key": "product_name", "label": "Product", "width": 34},
        {"key": "mrp", "label": "MRP", "format": "money"},
        {"key": "qty", "label": "Qty", "format": "num1"},
        {"key": "actual_cost", "label": "Actual Cost", "format": "money"},
        {"key": "nmw_low_rate", "label": "NMW Low Rate", "format": "money"},
        {"key": "nmw_rate_source", "label": "NMW Rate Source", "width": 30},
        {"key": "unit", "label": "Unit"},
        {"key": "unit_mismatch", "label": "Unit Mismatch?"},
        {"key": "loss", "label": "Loss", "format": "money"},
    ]
    product_rows = [{"product_code": p["product_code"], "product_name": p["product_name"],
                      "total_loss": p["total_loss"]} for p in res["top_products"]]
    return _xlsx({
        "title": f"NMW vs {body.tenant} - Rate Variance ({'batch-wise' if res['batch_wise'] else 'bill-wise'})",
        "notes": [
            f"YTD total loss: {res['ytd_total_loss']:,.2f}. Generated {res['generated_at']}.",
            "Benchmark = NMW's single fixed lowest outlier-filtered rate per (product name, MRP) "
            "variant, over the full window -- same rate compared against every real purchase line.",
            f"{res['unit_mismatch_count']} line(s) flagged with a differing sale/purchase unit between "
            f"NMW and this tenant; {res['unit_unknown_count']} line(s) have no unit recorded on either "
            "side and were NOT assumed equivalent.",
            f"{res['unmatched_mrp_lines']} purchase line(s) matched a selected product by name but not "
            "by MRP, so were left out rather than compared against the wrong variant's rate.",
        ],
        "sheets": [
            {"name": "Top 25 Products", "columns": _PRODUCT_COLS, "rows": product_rows},
            {"name": "Monthwise", "columns": _MONTH_COLS, "rows": res["monthwise"]},
            {"name": f"{res['group_field'].replace('_', ' ').title()}-wise Detail", "columns": bill_cols,
             "rows": res["bill_rows"]},
        ],
    }, f"NMW_vs_{body.tenant}_Variance")
