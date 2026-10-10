"""Tests for the store-scoped auth relaxation on the Legacy Order console.

require_order_console_access lets a non-admin STORE user work their OWN store's
order from outside the LAN (the Order Management desktop client): read its
views, and do the interactive mutations (edit OrderQty / qty-check, assign a
supplier, export). It must still block another store, and every admin-only
trigger (sync / order-process / stock-update / workflow finalize), for a store
user. Admins keep full access. No app/DB wiring -- the function takes a request
and a user dict, so a tiny fake request is enough.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from modules.legacy_order import router as lo


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeRequest:
    def __init__(self, method, path, path_params):
        self.method = method
        self.url = _FakeURL(path)
        self.path_params = path_params


# --- users ---------------------------------------------------------------
ADMIN = {"is_platform_user": True, "role_names": ["PLATFORM_OWNER"], "store_code": None}
SUPER = {"is_platform_user": False, "role_names": ["SUPER_ADMIN"], "store_code": None}
NMV_USER = {"is_platform_user": False, "role_names": ["PURCHASE_MANAGER"], "store_code": "NMV", "sub": "u1", "username": "nmvpm"}


def _allow(method, path, path_params, user):
    return lo.require_order_console_access(_FakeRequest(method, path, path_params), user)


def _denied(method, path, path_params, user):
    with pytest.raises(HTTPException) as ei:
        _allow(method, path, path_params, user)
    assert ei.value.status_code == 403


# --- store user may work THEIR OWN store ---------------------------------

def test_store_user_reads_own_store():
    assert _allow("GET", "/api/legacy-order/orders/NMV", {"store_name": "NMV"}, NMV_USER) is NMV_USER
    assert _allow("GET", "/api/legacy-order/qty-check/NMV", {"store_name": "NMV"}, NMV_USER) is NMV_USER


def test_store_user_interactive_mutations_own_store():
    assert _allow("PATCH", "/api/legacy-order/orders/NMV/123", {"store_name": "NMV", "product_code": "123"}, NMV_USER) is NMV_USER
    assert _allow("POST", "/api/legacy-order/orders/NMV/123/assign", {"store_name": "NMV", "product_code": "123"}, NMV_USER) is NMV_USER
    assert _allow("POST", "/api/legacy-order/orders/NMV/export", {"store_name": "NMV"}, NMV_USER) is NMV_USER
    assert _allow("PATCH", "/api/legacy-order/qty-check/NMV/123", {"store_name": "NMV", "product_code": "123"}, NMV_USER) is NMV_USER


# --- store user may NOT cross stores -------------------------------------

def test_store_user_blocked_on_other_store():
    _denied("GET", "/api/legacy-order/orders/NMC", {"store_name": "NMC"}, NMV_USER)
    _denied("PATCH", "/api/legacy-order/orders/NMC/123", {"store_name": "NMC", "product_code": "123"}, NMV_USER)
    _denied("POST", "/api/legacy-order/orders/NMC/export", {"store_name": "NMC"}, NMV_USER)


# --- store user may NOT reach admin-only triggers ------------------------

def test_store_user_blocked_on_admin_triggers():
    # sync / order-process / stock-update carry store_name in the BODY, not the
    # path, so there is no path param to own -> denied.
    _denied("POST", "/api/legacy-order/sync", {}, NMV_USER)
    _denied("POST", "/api/legacy-order/order-process", {}, NMV_USER)
    _denied("POST", "/api/legacy-order/stock-update", {}, NMV_USER)
    _denied("POST", "/api/legacy-order/compare-previous-order", {}, NMV_USER)
    # finalize/reopen are store-path but NOT in the interactive write set.
    _denied("POST", "/api/legacy-order/orders/NMV/workflow/finalize", {"store_name": "NMV"}, NMV_USER)
    _denied("POST", "/api/legacy-order/orders/NMV/workflow/reopen", {"store_name": "NMV"}, NMV_USER)
    # DB recovery has no store param at all.
    _denied("POST", "/api/legacy-order/db/recover", {}, NMV_USER)


# --- admins keep full access ---------------------------------------------

def test_admin_full_access():
    for u in (ADMIN, SUPER):
        assert _allow("POST", "/api/legacy-order/sync", {}, u) is u
        assert _allow("POST", "/api/legacy-order/orders/NMC/export", {"store_name": "NMC"}, u) is u
        assert _allow("GET", "/api/legacy-order/orders/ANY", {"store_name": "ANY"}, u) is u
