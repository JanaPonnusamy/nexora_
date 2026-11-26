"""PM access to Pending Supply Review writes through the router-level gate."""
import pytest
from fastapi import HTTPException

from modules.legacy_order import router as r


class _Req:
    def __init__(self, method, path, store="SMG"):
        self.method = method
        self.url = type("U", (), {"path": path})()
        self.path_params = {"store_name": store}


@pytest.fixture
def pm(monkeypatch):
    monkeypatch.setattr(r, "has_unrestricted_scope", lambda user: False)
    monkeypatch.setattr(r, "_user_store_codes", lambda user: {"SMG"})
    return {"role_names": ["Purchase Manager"], "sub": "u1"}


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/legacy-order/orders/SMG/gap-review/pending"),
    ("POST", "/api/legacy-order/orders/SMG/gap-review/pending/bulk"),
    ("POST", "/api/legacy-order/orders/SMG/gap-review/pending/clear"),
    ("POST", "/api/legacy-order/orders/SMG/gap-review/complete"),
    ("DELETE", "/api/legacy-order/orders/SMG/gap-review/pending/42"),
    ("POST", "/api/legacy-order/orders/SMG/order-entry"),
    ("GET", "/api/legacy-order/orders/SMG/gap-review"),
])
def test_pm_can_work_pending_supply_review(pm, method, path):
    assert r.require_order_console_access(_Req(method, path), pm) is pm


def test_pm_cannot_touch_another_store(pm):
    with pytest.raises(HTTPException):
        r.require_order_console_access(_Req("POST", "/api/legacy-order/orders/SMA/gap-review/complete", "SMA"), pm)


def test_store_user_who_is_not_pm_cannot_sign_off(pm):
    clerk = {"role_names": ["Store Staff"], "sub": "u2"}
    with pytest.raises(HTTPException):
        r.require_order_console_access(_Req("POST", "/api/legacy-order/orders/SMG/gap-review/complete"), clerk)
