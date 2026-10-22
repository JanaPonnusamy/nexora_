"""Server-side authorization checks for the six procurement mutation routes
flagged in the rare-mover safety audit as having no procurement-specific
capability check and no tenant-ownership verification: assign, bulk_assign,
change_supplier, remove_assignment, export, submit_grn.

Does not open SQL Server. Module codes are injected the same way
tests/test_procurement_rules_auth.py already does (access.load_module_codes
replaced via monkeypatch). The underlying service functions are monkeypatched
too, so a request that passes authorization never reaches get_connection() --
this test file verifies the router-level gate only, not business behavior
already covered elsewhere (test_procurement_decision_engine.py,
test_vpl_history*.py).
"""

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from config.security import create_access_token  # noqa: E402
from modules.procurement import access  # noqa: E402
from modules.procurement import assignment_service, export_service, reconciliation_service  # noqa: E402
from modules.procurement.pm_router import router  # noqa: E402

app = FastAPI()
app.include_router(router, prefix="/api/procurement")
client = TestClient(app)

_SENTINEL = {"ok": True}


def _token(**claims):
    body = {
        "sub": "user-1",
        "tenant_id": "tenant-a",
        "is_platform_user": False,
        "role_names": ["PURCHASE_MANAGER"],
    }
    body.update(claims)
    return create_access_token(body)


def _auth(token):
    return {"Authorization": "Bearer " + token}


def _stub_services(monkeypatch):
    """Replace every service call this test file exercises with a sentinel
    that never opens a connection -- if a route's authorization gate is
    bypassed, the test still cannot accidentally touch a real database; if
    the gate correctly rejects the request, these stubs are never called at
    all (asserted explicitly in the cross-tenant/forged-tenant tests)."""
    calls = []

    def _record(name):
        def _fn(*args, **kwargs):
            calls.append(name)
            return _SENTINEL
        return _fn

    monkeypatch.setattr(assignment_service, "assign_single", _record("assign_single"))
    monkeypatch.setattr(assignment_service, "assign_bulk", _record("assign_bulk"))
    monkeypatch.setattr(assignment_service, "change_supplier", _record("change_supplier"))
    monkeypatch.setattr(assignment_service, "remove_assignment", _record("remove_assignment"))
    monkeypatch.setattr(export_service, "export_refresh", _record("export_refresh"))
    monkeypatch.setattr(reconciliation_service, "submit_grn", _record("submit_grn"))
    return calls


_ROUTES = [
    ("POST", "/api/procurement/order-items/item-1/assignments",
     {"supplier_code": "SUP1", "qty": 5}),
    ("POST", "/api/procurement/assignments/bulk",
     {"supplier_code": "SUP1", "items": [{"order_item_id": "item-1"}]}),
    ("PUT", "/api/procurement/assignments/assign-1/supplier",
     {"supplier_code": "SUP2"}),
    ("DELETE", "/api/procurement/assignments/assign-1", None),
    ("POST", "/api/procurement/refreshes/refresh-1/export",
     {"exported_by": "user-1"}),
    ("POST", "/api/procurement/refreshes/refresh-1/grn",
     {"last_grn_number": "GRN-1"}),
]


def _call(method, path, body, headers=None, params=None):
    kwargs = {"headers": headers} if headers else {}
    if params:
        path = path + ("&" if "?" in path else "?") + params
    if method == "POST":
        return client.post(path, json=body, **kwargs)
    if method == "PUT":
        return client.put(path, json=body, **kwargs)
    if method == "DELETE":
        return client.delete(path, **kwargs)
    raise ValueError(method)


def test_all_six_routes_reject_unauthenticated_access(monkeypatch):
    calls = _stub_services(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    for method, path, body in _ROUTES:
        response = _call(method, path + "?tenant_id=tenant-a", body)
        assert response.status_code == 401, f"{method} {path} did not reject an unauthenticated request"
    assert calls == [], "no service function should run for an unauthenticated request"


def test_all_six_routes_reject_authenticated_but_unauthorized_role(monkeypatch):
    calls = _stub_services(monkeypatch)
    # A role with no procurement/purchase module grant at all.
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["INVENTORY_VIEW"])
    headers = _auth(_token())
    for method, path, body in _ROUTES:
        response = _call(method, path + "?tenant_id=tenant-a", body, headers=headers)
        assert response.status_code == 403, f"{method} {path} did not reject an unauthorized role"
    assert calls == [], "no service function should run for an unauthorized role"


def test_all_six_routes_reject_cross_tenant_access(monkeypatch):
    calls = _stub_services(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body in _ROUTES:
        response = _call(method, path + "?tenant_id=tenant-b", body, headers=headers)
        assert response.status_code == 403, f"{method} {path} allowed a cross-tenant request"
    assert calls == [], "no service function should run for a cross-tenant request"


def test_forged_tenant_id_does_not_grant_access(monkeypatch):
    """A caller authenticated for tenant-a cannot simply change the
    tenant_id query parameter to reach tenant-b's data -- restates the
    cross-tenant test with an explicitly adversarial framing (same
    mechanism, named for the specific threat model asked for)."""
    calls = _stub_services(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    response = _call(
        "POST", "/api/procurement/order-items/item-1/assignments?tenant_id=tenant-b",
        {"supplier_code": "SUP1", "qty": 5}, headers=headers,
    )
    assert response.status_code == 403
    assert "tenant-b" not in response.text, "the rejection must not echo the other tenant's id back"
    assert calls == []


def test_platform_user_passes_without_a_module_lookup(monkeypatch):
    def fail(user_id):
        raise AssertionError("platform users must not need a module lookup")

    monkeypatch.setattr(access, "load_module_codes", fail)
    calls = _stub_services(monkeypatch)
    headers = _auth(_token(is_platform_user=True, role_names=["PLATFORM_OWNER"], tenant_id="tenant-a"))
    response = _call(
        "POST", "/api/procurement/order-items/item-1/assignments?tenant_id=tenant-a",
        {"supplier_code": "SUP1", "qty": 5}, headers=headers,
    )
    assert response.status_code == 200
    assert calls == ["assign_single"]


def test_each_route_requires_its_matching_or_broader_capability(monkeypatch):
    """Export and GRN accept their own finer grant OR the coarse workspace
    grant (mirrors frontend/src/types/access.ts's 'a single coarse
    procurement grant unlocks the whole workspace' rule) -- but a grant for
    an unrelated procurement sub-capability alone is not tested here as a
    negative case, since the coarse-grant model deliberately treats any
    procurement/purchase module code as sufficient for workspace-tier
    actions. This test pins down that EXPORT-only and GRN-only grants work
    for their own route, and WORKSPACE-only also reaches every route."""
    calls = _stub_services(monkeypatch)
    headers = _auth(_token(tenant_id="tenant-a"))

    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_EXPORT"])
    response = _call(
        "POST", "/api/procurement/refreshes/refresh-1/export?tenant_id=tenant-a",
        {"exported_by": "user-1"}, headers=headers,
    )
    assert response.status_code == 200

    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_GRN"])
    response = _call(
        "POST", "/api/procurement/refreshes/refresh-1/grn?tenant_id=tenant-a",
        {"last_grn_number": "GRN-1"}, headers=headers,
    )
    assert response.status_code == 200

    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    for method, path, body in _ROUTES:
        response = _call(method, path + "?tenant_id=tenant-a", body, headers=headers)
        assert response.status_code == 200, f"{method} {path} rejected a coarse workspace grant"

    assert "export_refresh" in calls
    assert "submit_grn" in calls
    assert "assign_single" in calls


def test_unreadable_module_list_fails_closed(monkeypatch):
    calls = _stub_services(monkeypatch)

    def boom(user_id):
        raise RuntimeError("database offline")

    monkeypatch.setattr(access, "load_module_codes", boom)
    headers = _auth(_token())
    for method, path, body in _ROUTES:
        response = _call(method, path + "?tenant_id=tenant-a", body, headers=headers)
        assert response.status_code == 503, f"{method} {path} did not fail closed on an unreadable module list"
    assert calls == []


def test_bulk_assign_cross_tenant_request_is_rejected_before_any_item_is_touched(monkeypatch):
    """A bulk request naming several order_item_ids must be rejected in
    full at the authorization gate, not partially processed -- confirms
    the router-level check runs before assignment_service.assign_bulk's
    own per-item loop ever starts, so a cross-tenant bulk call cannot
    mutate even one of the named items."""
    calls = _stub_services(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))
    response = client.post(
        "/api/procurement/assignments/bulk?tenant_id=tenant-b",
        json={
            "supplier_code": "SUP1",
            "items": [{"order_item_id": "item-1"}, {"order_item_id": "item-2"}, {"order_item_id": "item-3"}],
        },
        headers=headers,
    )
    assert response.status_code == 403
    assert calls == [], "assign_bulk must never run, not even for a subset of the named items"


def test_authorized_same_tenant_requests_still_succeed_for_every_route(monkeypatch):
    """Confirms the fix does not break the existing authorized workflow --
    a correctly authenticated, same-tenant, procurement-capable caller
    still reaches the real service function for all six routes."""
    calls = _stub_services(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body in _ROUTES:
        response = _call(method, path + "?tenant_id=tenant-a", body, headers=headers)
        assert response.status_code == 200, f"{method} {path} broke an authorized same-tenant request"
    assert len(calls) == len(_ROUTES)
