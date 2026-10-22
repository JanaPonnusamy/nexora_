"""Server-side authorization checks for the Purchase Manager routes flagged by
the round-2 independent audit as missing a procurement capability check and/or
tenant-ownership verification: every route in pm_router.py except the six
already covered by test_procurement_pm_router_auth.py and the two genuinely
tenant-free routes (shelf_sort_category_vocab -- a fixed global vocabulary,
and supplier_stock_preview -- parses an upload without persisting anything).

Does not open SQL Server. Module codes are injected the same way
test_procurement_pm_router_auth.py already does (access.load_module_codes
replaced via monkeypatch). Every underlying service/distribution function this
file exercises is monkeypatched too, so a request that passes authorization
never reaches get_connection() -- including distribution_service.generate,
which would otherwise attempt a real WhatsApp send; this file guarantees that
never happens, by construction, for every test here.

distribution_run_detail/distribution_retry/distribution_run_item_products/
distribution_run_item_send_whatsapp take no tenant_id parameter at all -- the
fix added a trusted server-side lookup (distribution_service.run_tenant_id /
run_item_tenant_id) that these tests monkeypatch directly to simulate "this
run/run_item belongs to tenant-b" without touching a real distribution_run row.
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
from modules.procurement import (  # noqa: E402
    assignment_service,
    distribution_service,
    export_document_service,
    export_service,
    pending_service,
    shelf_sort_service,
    supplier_service,
    supplier_stock_service,
    supplier_reply_service,
    reconciliation_repository,
    workspace_service,
)
from modules.procurement.pm_router import router  # noqa: E402

app = FastAPI()
app.include_router(router, prefix="/api/procurement")
client = TestClient(app)

_SENTINEL = {"ok": True}
_REFRESH_ROW = {"cycle_id": "cyc-1", "store_id": "store-1"}


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


def _stub_all(monkeypatch):
    """Monkeypatch every service/repository entry point this file's routes
    can reach, recording call names -- if a route's gate is bypassed, nothing
    here ever opens a real connection; if the gate rejects correctly, the
    matching name must never appear in `calls` (asserted in the cross-tenant
    tests)."""
    calls = []

    def _record(name, result=None):
        def _fn(*args, **kwargs):
            calls.append(name)
            return result if result is not None else _SENTINEL
        return _fn

    monkeypatch.setattr(workspace_service, "get_item", _record("get_item"))
    monkeypatch.setattr(workspace_service, "set_final_qty", _record("set_final_qty"))
    monkeypatch.setattr(workspace_service, "restore_suggested", _record("restore_suggested"))
    monkeypatch.setattr(workspace_service, "skip_item", _record("skip_item"))
    monkeypatch.setattr(workspace_service, "restore_item", _record("restore_item"))
    monkeypatch.setattr(workspace_service, "defer_item", _record("defer_item"))
    monkeypatch.setattr(workspace_service, "get_decision", _record("get_decision"))

    monkeypatch.setattr(supplier_service, "get_queue", _record("get_queue"))
    monkeypatch.setattr(supplier_service, "get_queue_bulk", _record("get_queue_bulk"))
    monkeypatch.setattr(supplier_service, "products_for_supplier", _record("products_for_supplier"))
    monkeypatch.setattr(supplier_service, "search", _record("search"))
    monkeypatch.setattr(supplier_service, "stats", _record("stats"))
    monkeypatch.setattr(supplier_service, "list_settings", _record("list_settings"))
    monkeypatch.setattr(supplier_service, "update_settings", _record("update_settings"))
    monkeypatch.setattr(supplier_service, "get_export_settings", _record("get_export_settings"))
    monkeypatch.setattr(supplier_service, "save_export_settings", _record("save_export_settings"))

    monkeypatch.setattr(supplier_stock_service, "list_supplier_stock", _record("list_supplier_stock"))
    monkeypatch.setattr(supplier_stock_service, "products_with_offers", _record("products_with_offers"))
    monkeypatch.setattr(supplier_stock_service, "get_mapping", _record("get_mapping"))
    monkeypatch.setattr(supplier_stock_service, "run_import", _record("run_import"))

    monkeypatch.setattr(distribution_service, "list_config", _record("list_config"))
    monkeypatch.setattr(distribution_service, "save_config", _record("save_config"))
    monkeypatch.setattr(distribution_service, "save_supplier_map", _record("save_supplier_map"))
    monkeypatch.setattr(distribution_service, "import_legacy_supplier_map", _record("import_legacy_supplier_map"))
    monkeypatch.setattr(distribution_service, "generate", _record("generate"))
    monkeypatch.setattr(distribution_service, "list_runs", _record("list_runs"))
    monkeypatch.setattr(distribution_service, "run_detail", _record("run_detail"))
    monkeypatch.setattr(distribution_service, "retry_failed", _record("retry_failed"))
    monkeypatch.setattr(distribution_service, "run_item_products", _record("run_item_products"))
    monkeypatch.setattr(distribution_service, "send_run_item_whatsapp", _record("send_run_item_whatsapp"))
    # Ownership lookups default to tenant-a -- authorized tests expect this;
    # cross-tenant tests override per-call via monkeypatch inside the test.
    monkeypatch.setattr(distribution_service, "run_tenant_id", lambda run_id: "tenant-a")
    monkeypatch.setattr(distribution_service, "run_item_tenant_id", lambda run_item_id: "tenant-a")

    monkeypatch.setattr(assignment_service, "list_for_item", _record("list_for_item"))
    monkeypatch.setattr(assignment_service, "list_for_refresh", _record("list_for_refresh"))

    monkeypatch.setattr(export_service, "history", _record("history"))
    monkeypatch.setattr(export_service, "batch_detail", _record("batch_detail"))
    monkeypatch.setattr(
        export_document_service, "build_document",
        _record("build_document", (b"x", "f.xlsx", "application/octet-stream")),
    )

    monkeypatch.setattr(
        shelf_sort_service, "collect_from_refresh",
        _record("collect_from_refresh", ([("f.xlsx", b"x")], 1)),
    )
    monkeypatch.setattr(
        shelf_sort_service, "collect_from_file",
        _record("collect_from_file", ([("f.xlsx", b"x")], 1)),
    )
    monkeypatch.setattr(shelf_sort_service, "review_uncategorised", _record("review_uncategorised", []))
    monkeypatch.setattr(shelf_sort_service, "classify_and_store", _record("classify_and_store", {}))
    monkeypatch.setattr(shelf_sort_service, "save_categories", _record("save_categories", {"saved": 0}))
    monkeypatch.setattr(
        shelf_sort_service, "bundle_response",
        lambda files, total, store_name: (b"x", "f.xlsx", "application/octet-stream", total, len(files)),
    )

    monkeypatch.setattr(supplier_reply_service, "preview_reply_import", _record("preview_reply_import"))
    monkeypatch.setattr(supplier_reply_service, "apply_reply_import", _record("apply_reply_import"))

    monkeypatch.setattr(pending_service, "list_pending", _record("list_pending"))
    monkeypatch.setattr(pending_service, "adjust", _record("adjust"))
    monkeypatch.setattr(pending_service, "skip", _record("skip"))
    monkeypatch.setattr(pending_service, "carry_forward", _record("carry_forward"))
    monkeypatch.setattr(pending_service, "finalize", _record("finalize"))
    monkeypatch.setattr(pending_service, "bulk", _record("bulk"))
    monkeypatch.setattr(pending_service, "report_xlsx", _record("report_xlsx", (b"x", "f.xlsx")))
    monkeypatch.setattr(pending_service, "add_manual", _record("add_manual"))

    monkeypatch.setattr(reconciliation_repository, "get_refresh", lambda tenant_id, refresh_id: dict(_REFRESH_ROW))

    return calls


# (method, path, json_body) -- every route is called with tenant_id=... (or,
# for the four run/run_item routes, no tenant_id at all) appended by the test.
_GET_ROUTES = [
    ("GET", "/api/procurement/order-items/item-1", None),
    ("GET", "/api/procurement/order-items/item-1/supplier-queue", None),
    ("GET", "/api/procurement/refreshes/refresh-1/supplier-recommendations", None),
    ("GET", "/api/procurement/refreshes/refresh-1/supplier-products?supplier_code=SUP1", None),
    ("GET", "/api/procurement/suppliers/search", None),
    ("GET", "/api/procurement/suppliers/SUP1/stats", None),
    ("GET", "/api/procurement/suppliers/settings?store_id=store-1", None),
    ("GET", "/api/procurement/suppliers/SUP1/export-settings?store_id=store-1", None),
    ("GET", "/api/procurement/refreshes/refresh-1/supplier-stock?supplier_code=SUP1", None),
    ("GET", "/api/procurement/refreshes/refresh-1/products-with-offers", None),
    ("GET", "/api/procurement/supplier-stock/mapping?store_id=store-1&supplier_code=SUP1", None),
    ("GET", "/api/procurement/distribution/config", None),
    ("GET", "/api/procurement/distribution/runs", None),
    ("GET", "/api/procurement/order-items/item-1/assignments", None),
    ("GET", "/api/procurement/refreshes/refresh-1/assignments", None),
    ("GET", "/api/procurement/refreshes/refresh-1/export-history", None),
    ("GET", "/api/procurement/exports/BATCH-1", None),
    ("GET", "/api/procurement/refreshes/refresh-1/shelf-sort/review", None),
    ("GET", "/api/procurement/refreshes/refresh-1/pending", None),
    ("GET", "/api/procurement/refreshes/refresh-1/pending/report", None),
    ("GET", "/api/procurement/order-items/item-1/decision", None),
]

_MUTATION_ROUTES = [
    ("PUT", "/api/procurement/order-items/item-1/final-qty", {"final_qty": 5}),
    ("POST", "/api/procurement/order-items/item-1/restore-suggested", {}),
    ("POST", "/api/procurement/order-items/item-1/skip", {"skip_reason": "x"}),
    ("POST", "/api/procurement/order-items/item-1/restore", {}),
    ("POST", "/api/procurement/order-items/item-1/defer", {}),
    ("PUT", "/api/procurement/suppliers/SUP1/settings?store_id=store-1", {}),
    ("PUT", "/api/procurement/suppliers/SUP1/export-settings?store_id=store-1", {}),
    ("PUT", "/api/procurement/distribution/config/store-1", {}),
    ("PUT", "/api/procurement/distribution/supplier-map/store-1?source_store_code=NMW&local_supplier_code=L1", {}),
    ("POST", "/api/procurement/distribution/supplier-map/import-legacy", {}),
    ("POST", "/api/procurement/distribution/generate?source_store_code=NMW", {}),
    ("POST", "/api/procurement/refreshes/refresh-1/export-document",
     {"items": [{"assignment_id": "a1", "qty": 1}]}),
    ("POST", "/api/procurement/refreshes/refresh-1/shelf-sort", {}),
    ("POST", "/api/procurement/shelf-sort/classify", {"names": ["x"]}),
    ("POST", "/api/procurement/shelf-sort/categories",
     {"entries": [{"name": "x", "category": "GENERAL"}]}),
    ("POST", "/api/procurement/refreshes/refresh-1/supplier-reply/import",
     {"rows": [{"assignment_id": "a1"}]}),
    ("PUT", "/api/procurement/order-items/item-1/pending", {"remaining_qty": 1}),
    ("POST", "/api/procurement/order-items/item-1/pending/skip", {}),
    ("POST", "/api/procurement/order-items/item-1/pending/carry-forward", {}),
    ("POST", "/api/procurement/refreshes/refresh-1/pending/finalize", {}),
    ("POST", "/api/procurement/refreshes/refresh-1/pending/bulk",
     {"action": "carry", "order_item_ids": ["item-1"]}),
    ("POST", "/api/procurement/refreshes/refresh-1/manual-items",
     {"product_code": "P1", "qty": 1}),
]

# Four routes with NO tenant_id parameter at all -- authorized via a trusted
# server-side lookup (run_tenant_id / run_item_tenant_id) instead.
_RUN_ROUTES = [
    ("GET", "/api/procurement/distribution/runs/run-1", None),
    ("POST", "/api/procurement/distribution/runs/run-1/retry", {}),
    ("GET", "/api/procurement/distribution/run-items/ri-1/products", None),
    ("POST", "/api/procurement/distribution/run-items/ri-1/send-whatsapp", {}),
]

# D8 (owner-approved, 2026-10-21): all 10 distribution_* handlers now require
# require_procurement_admin, not require_procurement_workspace -- matching the
# admin-only frontend route /procurement/distribution. (method, path, body,
# service_call_name) -- service_call_name is the name _stub_all records, used
# to assert the underlying action never ran for a denied caller.
_DISTRIBUTION_ROUTES = [
    ("GET", "/api/procurement/distribution/config", None, "list_config"),
    ("PUT", "/api/procurement/distribution/config/store-1", {}, "save_config"),
    ("PUT", "/api/procurement/distribution/supplier-map/store-1?source_store_code=NMW&local_supplier_code=L1",
     {}, "save_supplier_map"),
    ("POST", "/api/procurement/distribution/supplier-map/import-legacy", {}, "import_legacy_supplier_map"),
    ("POST", "/api/procurement/distribution/generate?source_store_code=NMW", {}, "generate"),
    ("GET", "/api/procurement/distribution/runs", None, "list_runs"),
    ("GET", "/api/procurement/distribution/runs/run-1", None, "run_detail"),
    ("POST", "/api/procurement/distribution/runs/run-1/retry", {}, "retry_failed"),
    ("GET", "/api/procurement/distribution/run-items/ri-1/products", None, "run_item_products"),
    ("POST", "/api/procurement/distribution/run-items/ri-1/send-whatsapp", {}, "send_run_item_whatsapp"),
]
# The four run-based routes take no tenant_id query param -- same split as
# _RUN_ROUTES above, needed because _with_tenant only applies to the other six.
_DISTRIBUTION_RUN_BASED_PATHS = {
    "/api/procurement/distribution/runs/run-1",
    "/api/procurement/distribution/runs/run-1/retry",
    "/api/procurement/distribution/run-items/ri-1/products",
    "/api/procurement/distribution/run-items/ri-1/send-whatsapp",
}


def _call(method, path, body, headers=None):
    kwargs = {"headers": headers} if headers else {}
    if method == "GET":
        return client.get(path, **kwargs)
    if method == "PUT":
        return client.put(path, json=body, **kwargs)
    if method == "POST":
        return client.post(path, json=body, **kwargs)
    raise ValueError(method)


def _with_tenant(path, tenant_id):
    return path + ("&" if "?" in path else "?") + f"tenant_id={tenant_id}"


def test_all_routes_reject_unauthenticated_access(monkeypatch):
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    for method, path, body in _GET_ROUTES + _MUTATION_ROUTES:
        response = _call(method, _with_tenant(path, "tenant-a"), body)
        assert response.status_code == 401, f"{method} {path} did not reject an unauthenticated request"
    for method, path, body in _RUN_ROUTES:
        response = _call(method, path, body)
        assert response.status_code == 401, f"{method} {path} did not reject an unauthenticated request"
    assert calls == [], "no service function should run for an unauthenticated request"


def test_all_routes_reject_unauthorized_role(monkeypatch):
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["INVENTORY_VIEW"])
    headers = _auth(_token())
    for method, path, body in _GET_ROUTES + _MUTATION_ROUTES:
        response = _call(method, _with_tenant(path, "tenant-a"), body, headers=headers)
        assert response.status_code == 403, f"{method} {path} did not reject an unauthorized role"
    for method, path, body in _RUN_ROUTES:
        response = _call(method, path, body, headers=headers)
        assert response.status_code == 403, f"{method} {path} did not reject an unauthorized role"
    assert calls == [], "no service function should run for an unauthorized role"


def test_all_routes_reject_cross_tenant_forged_tenant_id(monkeypatch):
    """Authenticated for tenant-a; the tenant_id query parameter is forged to
    tenant-b. Every route must reject before its service function runs -- this
    is the exact shape of the vulnerability the round-2 audit confirmed."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body in _GET_ROUTES + _MUTATION_ROUTES:
        response = _call(method, _with_tenant(path, "tenant-b"), body, headers=headers)
        assert response.status_code == 403, f"{method} {path} allowed a forged cross-tenant tenant_id"
    assert calls == [], "no service function should run for a forged tenant_id"


def test_run_routes_reject_a_run_owned_by_another_tenant(monkeypatch):
    """distribution_run_detail/retry/run_item_products/send_run_item_whatsapp
    take no tenant_id parameter -- authorization instead depends on the
    trusted run_tenant_id/run_item_tenant_id lookup. Simulate a run/run_item
    that belongs to tenant-b while the caller is authenticated for tenant-a."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(distribution_service, "run_tenant_id", lambda run_id: "tenant-b")
    monkeypatch.setattr(distribution_service, "run_item_tenant_id", lambda run_item_id: "tenant-b")
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body in _RUN_ROUTES:
        response = _call(method, path, body, headers=headers)
        assert response.status_code == 403, f"{method} {path} allowed access to another tenant's run"
    assert calls == [], "no distribution action should run against another tenant's run"


def test_run_routes_404_when_the_run_does_not_exist(monkeypatch):
    """A run_id/run_item_id that resolves to no owning tenant at all (deleted,
    typo'd, never existed) must 404, not silently proceed or leak a 403 that
    would otherwise imply the row exists."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(distribution_service, "run_tenant_id", lambda run_id: None)
    monkeypatch.setattr(distribution_service, "run_item_tenant_id", lambda run_item_id: None)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body in _RUN_ROUTES:
        response = _call(method, path, body, headers=headers)
        assert response.status_code == 404, f"{method} {path} did not 404 for a nonexistent run"
    assert calls == []


def test_bulk_pending_cross_tenant_request_is_rejected_before_any_item_is_touched(monkeypatch):
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))
    response = client.post(
        "/api/procurement/refreshes/refresh-1/pending/bulk?tenant_id=tenant-b",
        json={"action": "carry", "order_item_ids": ["item-1", "item-2", "item-3"]},
        headers=headers,
    )
    assert response.status_code == 403
    assert calls == [], "pending_service.bulk must never run for a forged cross-tenant request"


def test_unreadable_module_list_fails_closed(monkeypatch):
    calls = _stub_all(monkeypatch)

    def boom(user_id):
        raise RuntimeError("database offline")

    monkeypatch.setattr(access, "load_module_codes", boom)
    headers = _auth(_token())
    for method, path, body in _GET_ROUTES + _MUTATION_ROUTES:
        response = _call(method, _with_tenant(path, "tenant-a"), body, headers=headers)
        assert response.status_code == 503, f"{method} {path} did not fail closed on an unreadable module list"
    for method, path, body in _RUN_ROUTES:
        response = _call(method, path, body, headers=headers)
        assert response.status_code == 503, f"{method} {path} did not fail closed on an unreadable module list"
    assert calls == []


def test_authorized_same_tenant_requests_still_succeed(monkeypatch):
    """Confirms the fix does not break the existing authorized workflow for
    any of the newly-gated routes."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body in _GET_ROUTES + _MUTATION_ROUTES:
        response = _call(method, _with_tenant(path, "tenant-a"), body, headers=headers)
        assert response.status_code == 200, f"{method} {path} broke an authorized same-tenant request"
    for method, path, body in _RUN_ROUTES:
        response = _call(method, path, body, headers=headers)
        assert response.status_code == 200, f"{method} {path} broke an authorized same-tenant request"
    assert len(calls) == len(_GET_ROUTES) + len(_MUTATION_ROUTES) + len(_RUN_ROUTES)


def test_distribution_generate_never_runs_for_an_unauthorized_caller(monkeypatch):
    """Specific regression for the real-side-effect route: confirms generate
    (which would send real WhatsApp messages against live code) is never
    invoked for a cross-tenant or unauthorized-role caller -- this test would
    fail loudly (AssertionError, not a WhatsApp send) if the gate regressed,
    since distribution_service.generate is monkeypatched to a sentinel here."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["INVENTORY_VIEW"])
    headers = _auth(_token(tenant_id="tenant-a"))
    response = client.post(
        "/api/procurement/distribution/generate?tenant_id=tenant-a&source_store_code=NMW",
        json={}, headers=headers,
    )
    assert response.status_code == 403
    assert "generate" not in calls


def test_supplier_stock_import_requires_authorization(monkeypatch):
    """The destructive REPLACE-shaped supplier_stock_import route, confirmed
    vulnerable by the round-2 audit, via a real multipart POST (not covered
    by _MUTATION_ROUTES since it needs file+form, not json)."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))

    files = {"file": ("stock.xlsx", b"fake", "application/octet-stream")}
    data = {"mapping": "{}"}

    # Cross-tenant forged tenant_id must reject before run_import is called.
    response = client.post(
        "/api/procurement/supplier-stock/import?tenant_id=tenant-b&store_id=store-1&supplier_code=SUP1",
        files=files, data=data, headers=headers,
    )
    assert response.status_code == 403
    assert "run_import" not in calls

    # Same-tenant authorized request still works.
    response = client.post(
        "/api/procurement/supplier-stock/import?tenant_id=tenant-a&store_id=store-1&supplier_code=SUP1",
        files=files, data=data, headers=headers,
    )
    assert response.status_code == 200
    assert "run_import" in calls


def test_shelf_sort_upload_requires_authorization(monkeypatch):
    """shelf_sort_upload needs a real multipart POST, not covered by
    _MUTATION_ROUTES."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))
    files = {"file": ("order.xlsx", b"fake", "application/octet-stream")}

    response = client.post(
        "/api/procurement/shelf-sort/upload?tenant_id=tenant-b&store_id=store-1",
        files=files, headers=headers,
    )
    assert response.status_code == 403
    assert "collect_from_file" not in calls

    response = client.post(
        "/api/procurement/shelf-sort/upload?tenant_id=tenant-a&store_id=store-1",
        files=files, headers=headers,
    )
    assert response.status_code == 200
    assert "collect_from_file" in calls


def test_supplier_reply_preview_requires_authorization(monkeypatch):
    """supplier_reply_preview needs a real multipart POST, not covered by
    _MUTATION_ROUTES."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))
    files = {"file": ("reply.xlsx", b"fake", "application/octet-stream")}

    response = client.post(
        "/api/procurement/refreshes/refresh-1/supplier-reply/preview?tenant_id=tenant-b",
        files=files, headers=headers,
    )
    assert response.status_code == 403
    assert "preview_reply_import" not in calls

    response = client.post(
        "/api/procurement/refreshes/refresh-1/supplier-reply/preview?tenant_id=tenant-a",
        files=files, headers=headers,
    )
    assert response.status_code == 200
    assert "preview_reply_import" in calls


def test_genuinely_tenant_free_routes_remain_unauthenticated_safe(monkeypatch):
    """shelf_sort_category_vocab (fixed global vocabulary) and
    supplier_stock_preview (parses an upload, persists nothing) were
    classified SAFE by the round-2 audit and intentionally left ungated at
    the router level, because they expose no tenant-scoped data and mutate
    nothing.

    IMPORTANT CAVEAT, not glossed over: this test app mounts only
    pm_router.router, not the real app.py -- it does NOT include app.py's
    global require_auth middleware (the thing that actually gives these two
    routes their 401-with-no-token behavior in the real deployed app, since
    /api/procurement/* is not in that middleware's allowlist). Inside this
    isolated test app, a route with zero local Depends is reachable with no
    token at all, by construction -- this test documents and asserts that
    real, narrower behavior instead of a false claim of route-level auth.
    A genuine end-to-end check of app.py's middleware would need the full
    app, which is out of scope for this router-only test file."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(supplier_stock_service, "preview_import", lambda *a, **k: {"headers": []})

    response = client.get("/api/procurement/shelf-sort/categories")
    assert response.status_code == 200, (
        "shelf_sort_category_vocab has no local Depends by design (global "
        "vocabulary, no tenant data) -- in this isolated router-only test "
        "app it is reachable with no token; app.py's global middleware is "
        "what protects it in the real deployment, and is not mounted here."
    )

    headers = _auth(_token())
    response = client.get("/api/procurement/shelf-sort/categories", headers=headers)
    assert response.status_code == 200

    files = {"file": ("stock.xlsx", b"fake", "application/octet-stream")}
    response = client.post(
        "/api/procurement/supplier-stock/preview?tenant_id=tenant-a&store_id=store-1&supplier_code=SUP1",
        files=files, headers=headers,
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------
# D8 (owner-approved, 2026-10-21): distribution_* now requires
# require_procurement_admin, not require_procurement_workspace.
# --------------------------------------------------------------------------

def _call_distribution(method, path, body, tenant_id, headers):
    if path in _DISTRIBUTION_RUN_BASED_PATHS:
        return _call(method, path, body, headers=headers)
    return _call(method, _with_tenant(path, tenant_id), body, headers=headers)


def test_distribution_routes_reject_workspace_only_grant(monkeypatch):
    """The exact gap D8 closes: a caller with ONLY PROCUREMENT_WORKSPACE (no
    admin grant) must now be rejected on every one of the 10 distribution_*
    routes, even though they are fully authenticated, same-tenant, and would
    have passed before this task (require_procurement_workspace accepted any
    procurement/purchase module code). This is the test the existing round-2
    suite was missing -- every one of its own distribution checks happened to
    use PROCUREMENT_ADMIN, which also satisfies require_procurement_workspace,
    so it could not have caught this regression on its own."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body, service_name in _DISTRIBUTION_ROUTES:
        response = _call_distribution(method, path, body, "tenant-a", headers)
        assert response.status_code == 403, (
            f"{method} {path} allowed a PROCUREMENT_WORKSPACE-only caller — "
            "D8 requires PROCUREMENT_ADMIN on every distribution_* route"
        )
        assert service_name not in calls, (
            f"{service_name} must never run for a workspace-only caller on {path}"
        )
    assert calls == [], "no distribution action should run for a workspace-only caller"


def test_distribution_routes_accept_admin_grant(monkeypatch):
    """The positive side of the same boundary: a caller holding
    PROCUREMENT_ADMIN, same tenant, still reaches every one of the 10
    distribution_* routes -- D8 must not break the legitimate admin
    workflow it is meant to preserve."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body, service_name in _DISTRIBUTION_ROUTES:
        response = _call_distribution(method, path, body, "tenant-a", headers)
        assert response.status_code == 200, (
            f"{method} {path} rejected an authorized PROCUREMENT_ADMIN caller"
        )
        assert service_name in calls, f"{service_name} should have run for {path}"


def test_distribution_routes_still_reject_cross_tenant_even_with_admin_grant(monkeypatch):
    """PROCUREMENT_ADMIN alone must not bypass tenant isolation -- D8 adds a
    stricter capability floor, it does not relax assert_tenant_access. Covers
    the six tenant_id-parameterized distribution routes (the four run-based
    routes have their own dedicated cross-tenant test above,
    test_run_routes_reject_a_run_owned_by_another_tenant)."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    headers = _auth(_token(tenant_id="tenant-a"))
    for method, path, body, service_name in _DISTRIBUTION_ROUTES:
        if path in _DISTRIBUTION_RUN_BASED_PATHS:
            continue
        response = _call(method, _with_tenant(path, "tenant-b"), body, headers=headers)
        assert response.status_code == 403, f"{method} {path} allowed a forged cross-tenant tenant_id for an admin"
        assert service_name not in calls
    assert calls == []


def test_distribution_routes_fail_closed_on_unreadable_module_list(monkeypatch):
    """D8 reuses require_procurement_admin, which already fails closed (503)
    identically to require_procurement_workspace -- confirms this did not
    regress for the distribution routes specifically."""
    calls = _stub_all(monkeypatch)

    def boom(user_id):
        raise RuntimeError("database offline")

    monkeypatch.setattr(access, "load_module_codes", boom)
    headers = _auth(_token())
    for method, path, body, service_name in _DISTRIBUTION_ROUTES:
        response = _call_distribution(method, path, body, "tenant-a", headers)
        assert response.status_code == 503, f"{method} {path} did not fail closed on an unreadable module list"
    assert calls == []


def test_distribution_routes_reject_unauthenticated_and_unauthorized_role(monkeypatch):
    """Baseline checks still hold post-D8: no token -> 401; an authenticated
    caller with no procurement/purchase module at all -> 403 (this case would
    also have been rejected pre-D8, included here for completeness alongside
    the new workspace-only-grant case above, not as new coverage on its own)."""
    calls = _stub_all(monkeypatch)
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["INVENTORY_VIEW"])
    headers = _auth(_token())
    for method, path, body, service_name in _DISTRIBUTION_ROUTES:
        response = _call_distribution(method, path, body, "tenant-a", None)
        assert response.status_code == 401, f"{method} {path} did not reject an unauthenticated request"
        response = _call_distribution(method, path, body, "tenant-a", headers)
        assert response.status_code == 403, f"{method} {path} did not reject a no-module-at-all role"
    assert calls == []
