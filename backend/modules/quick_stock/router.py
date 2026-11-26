"""Quick Stock API — lightweight, no-login stock lookup across all branches.

Gated by a single shared passcode (QUICK_STOCK_PIN), not the normal JWT
session: this is a kiosk-style page meant to open and search instantly on any
store PC, with no per-user login. The PIN check happens here (via the
x-quick-stock-pin header), not in api/app.py's JWT middleware, so these paths
are listed in app.py's _PUBLIC_API_PATHS / exempt patterns.

Production (.73) sets QUICK_STOCK_PIN to a long random token in config\\ho.env
rather than using this module's short dev default -- the token is baked into
the desktop client's quick-stock-config.json at build time and injected into
the page silently (see desktop/quick-stock-client/electron/main.cjs), so a
counter operator never sees or types anything. It is the SAME trust model as
a shared PIN, not a per-device credential: anyone who extracts it from the
distributed .exe can use it, same as anyone who learned a shared PIN could --
raising the bar past casual guessing, not providing device-level revocation.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException

from modules.quick_stock import service
from modules.quick_stock.schemas import CoreBulkRequest, CoreBulkSplitRequest, CrossStoreMatchRequest

router = APIRouter(prefix="/api/quick-stock", tags=["Quick Stock"])

_DEFAULT_PIN = "1234"


def _expected_pin() -> str:
    return os.getenv("QUICK_STOCK_PIN", _DEFAULT_PIN)


def _check_pin(pin: str | None) -> None:
    if not pin or pin != _expected_pin():
        raise HTTPException(status_code=401, detail="Invalid passcode")


@router.post("/verify")
def verify_pin(x_quick_stock_pin: str | None = Header(default=None)):
    """Used by the page's PIN prompt to confirm the code before storing it."""
    _check_pin(x_quick_stock_pin)
    return {"ok": True}


@router.get("/tenants")
def tenants(x_quick_stock_pin: str | None = Header(default=None)):
    _check_pin(x_quick_stock_pin)
    return service.list_tenants()


@router.get("/stores")
def stores(tenant_id: str, x_quick_stock_pin: str | None = Header(default=None)):
    """Store shells only (no products) -- lets the page draw every branch's
    fixed frame immediately on open, before any search is typed."""
    _check_pin(x_quick_stock_pin)
    return service.list_stores(tenant_id)


@router.get("/products/search")
def search_products(
    tenant_id: str,
    q: str = "",
    only_stock: int = 0,
    x_quick_stock_pin: str | None = Header(default=None),
):
    _check_pin(x_quick_stock_pin)
    return service.search_products(tenant_id, q, only_stock)


@router.get("/products/core")
def product_core(
    tenant_id: str,
    store_id: str,
    product: str,
    months: int = 3,
    x_quick_stock_pin: str | None = Header(default=None),
):
    _check_pin(x_quick_stock_pin)
    return service.product_core(tenant_id, store_id, product, months)


@router.get("/products/batches")
def batch_details(
    tenant_id: str,
    store_id: str,
    product: str,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Batches only -- mode-independent, used by the all-stores detail view's
    chart/batch panel so it never needs the bundled /products/core call."""
    _check_pin(x_quick_stock_pin)
    return service.batch_details(tenant_id, store_id, product)


@router.get("/products/movement")
def monthly_movement(
    tenant_id: str,
    store_id: str,
    product: str,
    months: int = 4,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Monthly movement only -- mode-independent (the chart always shows it,
    regardless of the Sales/Purchase toggle)."""
    _check_pin(x_quick_stock_pin)
    return service.monthly_movement(tenant_id, store_id, product, months)


@router.get("/products/purchases")
def purchase_history(
    tenant_id: str,
    store_id: str,
    product: str,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Purchases only -- fetched when the Purchase toggle is active, never
    alongside Sales (same result shape as /products/core's purchases set)."""
    _check_pin(x_quick_stock_pin)
    return service.purchase_history(tenant_id, store_id, product)


@router.get("/products/sales")
def sales_history(
    tenant_id: str,
    store_id: str,
    product: str,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Sales only -- fetched when the Sales toggle is active, never alongside
    Purchase (same result shape as /products/core's sales set)."""
    _check_pin(x_quick_stock_pin)
    return service.sales_history(tenant_id, store_id, product)


@router.post("/products/core/bulk")
def product_core_bulk(
    payload: CoreBulkRequest,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Parallel per-store core loading in one request -- avoids the DB
    contention that left most stores stuck on "Loading..." when the
    all-stores detail view issued one request per store."""
    _check_pin(x_quick_stock_pin)
    return service.product_core_bulk(payload.tenant_id, payload.items, payload.months)


@router.post("/products/core/bulk-split")
def product_core_bulk_split(
    payload: CoreBulkSplitRequest,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Sales/Purchase toggle, every store in one request: fetches batches +
    movement (always) plus ONLY the active mode's transactions -- the
    inactive type (Sales when Purchase is selected, or vice versa) is never
    queried."""
    _check_pin(x_quick_stock_pin)
    return service.product_core_bulk_split(payload.tenant_id, payload.items, payload.months, payload.mode)


@router.get("/products/bill")
def bill_items(
    tenant_id: str,
    store_id: str,
    bill_no: str,
    bill_date: str | None = None,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Full line-item breakdown of one bill (Latest Bill / bill-value drawer)."""
    _check_pin(x_quick_stock_pin)
    return service.bill_items(tenant_id, store_id, bill_no, bill_date)


@router.get("/products/grn")
def purchase_bill(
    tenant_id: str,
    store_id: str,
    grn_no: int,
    grn_date: str | None = None,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Full line-item breakdown of one GRN (Purchase Bill drawer), mirroring
    /products/bill for sales."""
    _check_pin(x_quick_stock_pin)
    return service.purchase_bill(tenant_id, store_id, grn_no, grn_date)


@router.post("/products/match")
def cross_store_match(
    payload: CrossStoreMatchRequest,
    x_quick_stock_pin: str | None = Header(default=None),
):
    """Resolve the equivalent product in each target store for a product
    selected in one store, via the real Product Mapping matcher (fixes the
    naive-name-match bug where stores with a slightly different product
    name silently dropped out of the all-stores detail row)."""
    _check_pin(x_quick_stock_pin)
    return service.cross_store_match(
        payload.tenant_id,
        payload.source_store_id,
        payload.source_product_code,
        payload.source_product_name,
        payload.target_store_ids,
    )
