"""Non-Moving Stock Analysis API (Stock Client "Non-Moving Stock").

Read-only analysis over sync.* -- no endpoint writes stock, creates a transfer
or changes Procurement data. POST is used only where the client sends a list
(transfer proposal / review list) and the answer is an Excel file.

Tenant-scoped. Super admins see every store; a purchase manager sees only
the store(s) of their active PURCHASE_MANAGER assignment (owner ruling
2026-11-02); everyone else is refused. The store must belong to the
tenant (checked server-side). Every list endpoint accepts ?format=xlsx and
then returns all filtered rows (not one page) as Excel.
"""

import re
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access, is_super_admin
from modules.nonmoving_analysis import repository as repo, service
from modules.rate_analysis import excel

router = APIRouter(prefix="/api/non-moving-analysis", tags=["Non-Moving Stock Analysis"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _assert_allowed(user: dict, tenant_id: str):
    """The caller's store scope: None = every store (super admin / platform
    user), else the set of STORE_IDs (upper case) a purchase manager is
    assigned to. Owner rulings: 2026-11-01 super admin only, 2026-11-02 plus
    each store's purchase manager for their own store."""
    if is_super_admin(user) or user.get("is_platform_user"):
        assert_tenant_access(user, tenant_id)
        return None
    names = [str(r or "").lower() for r in (user.get("role_names") or [])]
    if not any("purchase" in n for n in names):
        raise HTTPException(status_code=403, detail="Non-Moving Stock analysis is limited to super admin and purchase managers")
    assert_tenant_access(user, tenant_id)
    allowed = set(repo.purchase_manager_store_ids(user.get("sub") or user.get("user_id")))
    if not allowed and user.get("store_id"):
        allowed = {str(user["store_id"]).upper()}
    if not allowed:
        raise HTTPException(status_code=403, detail="No store is assigned to this purchase manager")
    return allowed


def _check_store(scope, store_id) -> None:
    if scope is not None and str(store_id or "").upper() not in scope:
        raise HTTPException(status_code=403, detail="You can only analyse your own store.")


def _xlsx(result: dict, name: str):
    # Header values must not carry stray whitespace / quotes (h11 rejects them).
    safe = re.sub(r"[^A-Za-z0-9 _.-]", "_", name).strip()
    return Response(content=excel.build_workbook(result), media_type=_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{safe}_{date.today():%Y-%m-%d}.xlsx"'})


def _cfg(bands, new_days, dest_cover_days, source_keep_days):
    return service.parse_config(bands, new_days, dest_cover_days, source_keep_days)


_OWN_COLS = [
    {"key": "product_code", "label": "Product Code", "width": 10},
    {"key": "product_name", "label": "Product Name", "width": 34},
    {"key": "unit", "label": "Unit", "width": 7},
    {"key": "pack", "label": "Pack", "width": 7},
    {"key": "product_type", "label": "Type", "width": 10},
    {"key": "stock", "label": "Current Stock", "format": "num1"},
    {"key": "batch_stock", "label": "Batch Stock", "format": "num1"},
    {"key": "cost_value", "label": "Stock Value (Cost)", "format": "money", "group": "Valuation"},
    {"key": "ptr_value", "label": "PTR Value", "format": "money", "group": "Valuation"},
    {"key": "mrp_value", "label": "MRP Value", "format": "money", "group": "Valuation"},
    {"key": "last_sale_date", "label": "Last Sale", "format": "date", "group": "Movement"},
    {"key": "days_since_sale", "label": "Days Since Sale", "format": "int", "group": "Movement"},
    {"key": "last_sale_source", "label": "Sale Source", "group": "Movement"},
    {"key": "sales_30", "label": "Sales 30d", "format": "num1", "group": "Movement"},
    {"key": "sales_90", "label": "Sales 90d", "format": "num1", "group": "Movement"},
    {"key": "last_purchase_date", "label": "Last Purchase", "format": "date"},
    {"key": "last_grn_date", "label": "Last GRN", "format": "date"},
    {"key": "supplier_name", "label": "Supplier", "width": 26},
    {"key": "expiry_status", "label": "Expiry Status", "width": 11},
    {"key": "earliest_expiry", "label": "Earliest Expiry", "format": "date"},
    {"key": "near_expiry_value", "label": "Near-Expiry Value", "format": "money"},
    {"key": "expired_value", "label": "Expired Value", "format": "money"},
    {"key": "classification_label", "label": "Classification", "width": 18},
    {"key": "flags_text", "label": "Flags", "width": 30},
]

_OTHER_COLS = [
    {"key": "product_code", "label": "Code", "width": 9},
    {"key": "product_name", "label": "Product Name", "width": 34},
    {"key": "stock", "label": "Stock Here", "format": "num1", "group": "This store"},
    {"key": "cost_value", "label": "Value (Cost)", "format": "money", "group": "This store"},
    {"key": "days_since_sale", "label": "Days Since Sale", "format": "int", "group": "This store"},
    {"key": "classification_label", "label": "Classification", "width": 18, "group": "This store"},
    {"key": "mapped_stores", "label": "Mapped Stores", "format": "int", "group": "Other stores"},
    {"key": "active_stores", "label": "Selling Stores", "format": "int", "group": "Other stores"},
    {"key": "other_stock", "label": "Their Stock", "format": "num1", "group": "Other stores"},
    {"key": "other_sales_30", "label": "Their Sales 30d", "format": "num1", "group": "Other stores"},
    {"key": "best_store", "label": "Best Store", "group": "Other stores"},
    {"key": "stores_text", "label": "Store detail (stock / 30d sales / days)", "width": 60},
]

_TRANSFER_COLS = [
    {"key": "product_name", "label": "Product", "width": 32},
    {"key": "source_store", "label": "From", "group": "Source"},
    {"key": "source_code", "label": "Code", "group": "Source"},
    {"key": "source_stock", "label": "Stock", "format": "num1", "group": "Source"},
    {"key": "source_days_since_sale", "label": "Days Since Sale", "format": "int", "group": "Source"},
    {"key": "source_classification_label", "label": "Class", "width": 16, "group": "Source"},
    {"key": "source_transferable", "label": "Transferable", "format": "num1", "group": "Source"},
    {"key": "dest_store", "label": "To", "group": "Destination"},
    {"key": "dest_code", "label": "Code", "group": "Destination"},
    {"key": "dest_stock", "label": "Stock", "format": "num1", "group": "Destination"},
    {"key": "dest_sales_30", "label": "Sales 30d", "format": "num1", "group": "Destination"},
    {"key": "dest_sales_90", "label": "Sales 90d", "format": "num1", "group": "Destination"},
    {"key": "dest_need", "label": "Need", "format": "num1", "group": "Destination"},
    {"key": "suggested_qty", "label": "Suggested Qty", "format": "num1", "group": "Proposal"},
    {"key": "suggested_packs", "label": "Packs", "format": "num1", "group": "Proposal"},
    {"key": "source_after", "label": "Source After", "format": "num1", "group": "Proposal"},
    {"key": "dest_after", "label": "Dest After", "format": "num1", "group": "Proposal"},
    {"key": "transfer_value", "label": "Value (Cost)", "format": "money", "group": "Proposal"},
    {"key": "reason", "label": "Reason", "width": 50},
    {"key": "calculation", "label": "Calculation", "width": 70},
]

_BLOCK_COLS = [
    {"key": "store_code", "label": "Store"},
    {"key": "product_code", "label": "Code"},
    {"key": "product_name", "label": "Product", "width": 32},
    {"key": "stock", "label": "Stock", "format": "num1"},
    {"key": "cost_value", "label": "Value (Cost)", "format": "money"},
    {"key": "classification_label", "label": "Classification", "width": 18},
    {"key": "reason", "label": "Why no transfer", "width": 50},
    {"key": "details_text", "label": "Per store", "width": 70},
]


def _flat_own(rows):
    return [{**r, "flags_text": ", ".join(r["flags"])} for r in rows]


@router.get("/stores")
def stores(tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    scope = _assert_allowed(current_user, tenant_id)
    stores = service.tenant_stores(tenant_id)
    if scope is not None:
        stores = [s for s in stores if str(s["store_id"]).upper() in scope]
    return {"stores": stores, "scope": "all" if scope is None else "own",
            "config": service.config_info(service.Config())}


@router.get("/own-store")
def own_store(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    search: Optional[str] = None,
    classes: Optional[str] = Query(None, description="comma list of classification keys"),
    ptype: Optional[str] = Query(None, description="pharma | nonpharma"),
    supplier: Optional[str] = None,
    min_days: Optional[int] = Query(None, ge=0),
    max_days: Optional[int] = Query(None, ge=0),
    expiry: Optional[str] = Query(None, description="expired | near | risk"),
    include_zero: bool = False,
    non_moving_only: bool = False,
    sort: str = "cost_value",
    direction: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=service.MAX_PAGE),
    refresh: bool = False,
    bands: Optional[str] = None,
    new_days: Optional[int] = Query(None, ge=1, le=730),
    format: str = "json",
    current_user: dict = Depends(get_current_user),
):
    scope = _assert_allowed(current_user, tenant_id)
    _check_store(scope, store_id)
    cfg = _cfg(bands, new_days, None, None)
    filters = dict(search=search, classes=classes, ptype=ptype, supplier=supplier, min_days=min_days,
                   max_days=max_days, expiry=expiry, include_zero=include_zero, non_moving_only=non_moving_only)
    xlsx = format.lower() == "xlsx"
    res = service.own_store(tenant_id, store_id, cfg, filters, sort, direction, page, page_size, refresh, all_rows=xlsx)
    if not xlsx:
        return res
    code = res["store"]["store_code"]
    return _xlsx({"title": f"Non-Moving Stock - {code} - Own Store Analysis",
                  "notes": [f"Data as of {res['refreshed_at']}. {res['config']['valuation']}",
                            "Days since sale = last valid sale (PSI; else POS rollup LastBillDate; else batch last sale)."],
                  "sheets": [{"name": "Own Store", "columns": _OWN_COLS, "rows": _flat_own(res["rows"])}]},
                 f"NonMoving_{code}")


@router.get("/product")
def product(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    product_code: str = Query(...),
    bands: Optional[str] = None,
    new_days: Optional[int] = Query(None, ge=1, le=730),
    current_user: dict = Depends(get_current_user),
):
    scope = _assert_allowed(current_user, tenant_id)
    _check_store(scope, store_id)
    return service.product_detail(tenant_id, store_id, product_code, _cfg(bands, new_days, None, None))


@router.get("/product/batches")
def product_batches(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    product_code: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    scope = _assert_allowed(current_user, tenant_id)
    _check_store(scope, store_id)
    return service.product_batches(tenant_id, store_id, product_code)


@router.get("/other-stores")
def other_stores(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    search: Optional[str] = None,
    scope: str = Query("selling", description="selling | all"),
    sort: str = "other_sales_30",
    direction: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=service.MAX_PAGE),
    refresh: bool = False,
    bands: Optional[str] = None,
    new_days: Optional[int] = Query(None, ge=1, le=730),
    format: str = "json",
    current_user: dict = Depends(get_current_user),
):
    scope = _assert_allowed(current_user, tenant_id)
    _check_store(scope, store_id)
    xlsx = format.lower() == "xlsx"
    res = service.other_stores(tenant_id, store_id, _cfg(bands, new_days, None, None), search, scope,
                               sort, direction, page, page_size, refresh, all_rows=xlsx)
    if not xlsx:
        return res
    rows = [{**r, "stores_text": "; ".join(
        f"{c['store_code']} {c['stock']:g} / {c['sales_30']:g} / {'-' if c['days_since_sale'] is None else c['days_since_sale']}"
        for c in r["stores"])} for r in res["rows"]]
    code = res["store"]["store_code"]
    return _xlsx({"title": f"Non-Moving Stock - {code} - Other Stores Analysis",
                  "notes": [f"Data as of {res['refreshed_at']}. Products non-moving at {code}, compared with every mapped store."],
                  "sheets": [{"name": "Other Stores", "columns": _OTHER_COLS, "rows": rows}]},
                 f"NonMoving_OtherStores_{code}")


@router.get("/transfers")
def transfers(
    tenant_id: str = Query(...),
    store_id: Optional[str] = None,
    direction: str = Query("all", description="out | in | all (relative to store_id)"),
    search: Optional[str] = None,
    sort: str = "transfer_value",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=service.MAX_PAGE),
    refresh: bool = False,
    bands: Optional[str] = None,
    new_days: Optional[int] = Query(None, ge=1, le=730),
    dest_cover_days: Optional[int] = Query(None, ge=1, le=365),
    source_keep_days: Optional[int] = Query(None, ge=1, le=365),
    format: str = "json",
    current_user: dict = Depends(get_current_user),
):
    scope = _assert_allowed(current_user, tenant_id)
    if scope is not None:
        _check_store(scope, store_id)     # a PM sees transfers into / out of their store only
    if store_id:
        service._store_of(tenant_id, store_id)
    cfg = _cfg(bands, new_days, dest_cover_days, source_keep_days)
    xlsx = format.lower() == "xlsx"
    res = service.transfers(tenant_id, store_id, cfg, direction, search, sort, order, page, page_size,
                            refresh, all_rows=xlsx)
    if not xlsx:
        return res
    return _transfer_xlsx(res, "Transfer Opportunities", "NonMoving_Transfers")


def _transfer_xlsx(res, title, name):
    blocks = [{**b, "details_text": "; ".join(b.get("details") or [])} for b in res.get("blocked_rows") or []]
    return _xlsx({"title": f"Non-Moving Stock - {title}",
                  "notes": [f"Data as of {res['refreshed_at']}. RECOMMENDATIONS ONLY - no stock has been moved.",
                            "Transferable excludes expired and near-expiry (90 days) batches and uses the lower of store and batch stock."],
                  "sheets": [{"name": "Recommendations", "columns": _TRANSFER_COLS, "rows": res["rows"]},
                             {"name": "No Transfer", "columns": _BLOCK_COLS, "rows": blocks}]},
                 name)


class ProposalBody(BaseModel):
    tenant_id: str
    store_id: Optional[str] = None
    ids: List[str]


@router.post("/transfers/proposal")
def transfer_proposal(body: ProposalBody, current_user: dict = Depends(get_current_user)):
    """Excel transfer PROPOSAL for the chosen recommendations. Prepares a
    document for the existing authorised transfer process -- executes nothing."""
    scope = _assert_allowed(current_user, body.tenant_id)
    ids = body.ids
    if scope is not None:
        # id = "<source store>|<code>|<dest store>|<code>": keep only lines touching their store
        ids = [i for i in ids if {p.upper() for p in i.split("|")[0::2]} & scope]
    if not ids:
        raise HTTPException(status_code=400, detail="Choose at least one recommendation")
    res = service.transfers(body.tenant_id, None, service.Config(), all_rows=True, ids=ids)
    res["blocked_rows"] = []
    return _transfer_xlsx(res, "Transfer Proposal (for approval)", "Transfer_Proposal")


@router.get("/dashboard")
def dashboard(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    refresh: bool = False,
    months: int = Query(6, ge=2, le=18),
    bands: Optional[str] = None,
    new_days: Optional[int] = Query(None, ge=1, le=730),
    format: str = "json",
    current_user: dict = Depends(get_current_user),
):
    scope = _assert_allowed(current_user, tenant_id)
    _check_store(scope, store_id)
    res = service.dashboard(tenant_id, store_id, _cfg(bands, new_days, None, None), refresh, months)
    if scope is not None:
        res["stores"] = [s for s in res["stores"] if str(s["store_id"]).upper() in scope]
    if format.lower() != "xlsx":
        return res
    store_cols = [
        {"key": "store_code", "label": "Store"},
        {"key": "products_analyzed", "label": "Products In Stock", "format": "int"},
        {"key": "stock_value", "label": "Stock Value (Cost)", "format": "money"},
        {"key": "non_moving_products", "label": "Non-Moving Products", "format": "int"},
        {"key": "non_moving_value", "label": "Non-Moving Value (Cost)", "format": "money"},
        {"key": "non_moving_mrp_value", "label": "Non-Moving Value (MRP)", "format": "money"},
        {"key": "dead_products", "label": "Dead Stock Products", "format": "int"},
        {"key": "dead_value", "label": "Dead Stock Value", "format": "money"},
        {"key": "expired_value", "label": "Expired Value", "format": "money"},
        {"key": "near_expiry_value", "label": "Near-Expiry Value", "format": "money"},
        {"key": "transfer_out", "label": "Transfers Out", "format": "int"},
        {"key": "transfer_in", "label": "Transfers In", "format": "int"},
    ]
    class_cols = [{"key": "label", "label": "Classification", "width": 22},
                  {"key": "products", "label": "Products", "format": "int"},
                  {"key": "qty", "label": "Qty", "format": "num1"},
                  {"key": "cost_value", "label": "Value (Cost)", "format": "money"},
                  {"key": "mrp_value", "label": "Value (MRP)", "format": "money"}]
    code = res["store"]["store_code"]
    return _xlsx({"title": f"Non-Moving Stock - {code} - Stock Value & Expiry Risk",
                  "notes": [f"Data as of {res['refreshed_at']}. {res['config']['valuation']}"],
                  "sheets": [{"name": "By Classification", "columns": class_cols, "rows": res["by_class"]},
                             {"name": "Store Comparison", "columns": store_cols, "rows": res["stores"]},
                             {"name": "Expiry Risk", "columns": _OWN_COLS, "rows": _flat_own(res["expiry_top"])}]},
                 f"NonMoving_Dashboard_{code}")


class ReviewItem(BaseModel):
    store_id: str
    product_code: str
    note: Optional[str] = None


class ReviewBody(BaseModel):
    tenant_id: str
    items: List[ReviewItem]


@router.post("/review/export")
def review_export(body: ReviewBody, current_user: dict = Depends(get_current_user)):
    """Excel of the user's manual-review list (the list itself lives on the
    client -- no database table exists for it yet)."""
    scope = _assert_allowed(current_user, body.tenant_id)
    items = [i.model_dump() for i in body.items
             if scope is None or str(i.store_id).upper() in scope]
    rows = service.review_rows(body.tenant_id, items, service.Config())
    cols = [{"key": "store_code", "label": "Store"}] + _OWN_COLS + [{"key": "note", "label": "Note", "width": 40}]
    return _xlsx({"title": "Non-Moving Stock - Manual Review List", "notes": [],
                  "sheets": [{"name": "Review", "columns": cols, "rows": _flat_own(rows)}]},
                 "NonMoving_Review")
