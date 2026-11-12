"""Quick Stock API — lightweight, no-login stock lookup across all branches.

Gated by a single shared passcode (QUICK_STOCK_PIN), not the normal JWT
session: this is a kiosk-style page meant to open and search instantly on any
store PC, with no per-user login. The PIN check happens here (via the
x-quick-stock-pin header), not in api/app.py's JWT middleware, so these paths
are listed in app.py's _PUBLIC_API_PATHS / exempt patterns.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException

from modules.quick_stock import service

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
