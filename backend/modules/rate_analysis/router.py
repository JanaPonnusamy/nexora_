"""Rate Analysis API — supplier purchase-rate tools (Stock Client "Rate Analysis").

Every report endpoint returns the uniform ``{title, notes, sheets}`` JSON, or the
same result as an .xlsx when called with ``?format=xlsx``. Tenant-scoped and
limited to super admins and purchase / admin roles (it exposes every store's
purchase rates); salesman logins are refused.
"""

import re
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access, is_super_admin
from modules.rate_analysis import excel, service

router = APIRouter(prefix="/api/rate-analysis", tags=["Rate Analysis"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _assert_allowed(user: dict, tenant_id: str) -> None:
    assert_tenant_access(user, tenant_id)
    if is_super_admin(user) or user.get("is_platform_user"):
        return
    names = [str(r or "").lower() for r in (user.get("role_names") or [])]
    if not any("purchase" in n or "admin" in n for n in names):
        raise HTTPException(status_code=403, detail="Rate Analysis is limited to purchase and admin logins")


def _out(result: dict, fmt: str, name: str):
    if (fmt or "json").lower() != "xlsx":
        return result
    # Header values must not carry stray whitespace / quotes (h11 rejects them).
    safe = re.sub(r"[^A-Za-z0-9 _.-]", "_", name).strip()
    filename = f"{safe}_{date.today():%Y-%m-%d}.xlsx"
    return Response(content=excel.build_workbook(result), media_type=_XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class QuoteMatchLine(BaseModel):
    text: str
    mrp: Optional[float] = None


class QuoteMatchBody(BaseModel):
    tenant_id: str
    lines: List[QuoteMatchLine]


class QuoteLine(BaseModel):
    text: Optional[str] = None
    label: Optional[str] = None
    key: Optional[str] = None
    mrp: Optional[float] = None
    ptr: Optional[float] = None


class QuoteCompareBody(BaseModel):
    tenant_id: str
    lines: List[QuoteLine]
    compare_days: int = Field(90, ge=7, le=730)
    sales_days: int = Field(90, ge=7, le=730)
    order_days: int = Field(30, ge=1, le=365)


class FastMoversBody(BaseModel):
    tenant_id: str
    supplier_keys: List[str]
    sales_days: int = Field(90, ge=7, le=730)
    rate_days: int = Field(30, ge=1, le=365)
    min_stores: int = Field(3, ge=1, le=50)
    exclude_names: List[str] = []


class RateDifferenceBody(BaseModel):
    tenant_id: str
    supplier_keys: List[str] = []
    date_from: date
    date_to: date
    check_gap_pct: float = Field(20.0, ge=1, le=500)


@router.get("/suppliers")
def suppliers(tenant_id: str = Query(...), days: int = Query(90, ge=7, le=730),
              current_user: dict = Depends(get_current_user)):
    _assert_allowed(current_user, tenant_id)
    return service.suppliers(tenant_id, days)


@router.post("/quote/match")
def quote_match(body: QuoteMatchBody, current_user: dict = Depends(get_current_user)):
    _assert_allowed(current_user, body.tenant_id)
    return service.quote_match(body.tenant_id, [ln.model_dump() for ln in body.lines])


@router.post("/quote/compare")
def quote_compare(body: QuoteCompareBody, format: str = Query("json"), current_user: dict = Depends(get_current_user)):
    _assert_allowed(current_user, body.tenant_id)
    result = service.quote_compare(body.tenant_id, [ln.model_dump() for ln in body.lines],
                                   body.compare_days, body.sales_days, body.order_days)
    return _out(result, format, "Quote_Compare_Order")


@router.post("/fast-movers")
def fast_movers(body: FastMoversBody, format: str = Query("json"), current_user: dict = Depends(get_current_user)):
    _assert_allowed(current_user, body.tenant_id)
    result = service.fast_movers(body.tenant_id, body.supplier_keys, body.sales_days, body.rate_days,
                                 body.min_stores, body.exclude_names)
    return _out(result, format, "Fast_Movers_Least_Rate")


@router.post("/rate-difference")
def rate_difference(body: RateDifferenceBody, format: str = Query("json"), current_user: dict = Depends(get_current_user)):
    _assert_allowed(current_user, body.tenant_id)
    result = service.rate_difference(body.tenant_id, body.supplier_keys, body.date_from, body.date_to, body.check_gap_pct)
    return _out(result, format, "Supplier_Rate_Difference")
