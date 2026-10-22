"""Server-side PROCUREMENT_ADMIN checks for the rules registry.

Does not open SQL Server. Module codes are injected by replacing
access.load_module_codes.
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
from modules.procurement.rules_router import router  # noqa: E402

app = FastAPI()
app.include_router(router, prefix="/api/procurement")
client = TestClient(app)


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


def test_catalog_requires_a_token(monkeypatch):
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_ADMIN"])
    response = client.get("/api/procurement/rules/catalog")
    assert response.status_code == 401


def test_workspace_capability_cannot_change_a_default(monkeypatch):
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_WORKSPACE"])
    response = client.put(
        "/api/procurement/rules/defaults/PRR-QTY-WINDOW",
        headers=_auth(_token()),
        json={"value": 60, "editor_id": "user-1", "reason": "no", "expected_version": 1},
    )
    assert response.status_code == 403


def test_admin_module_can_read_and_other_tenant_is_rejected(monkeypatch):
    monkeypatch.setattr(access, "load_module_codes", lambda user_id: ["PROCUREMENT_CYCLE"])
    headers = _auth(_token())
    allowed = client.get("/api/procurement/rules/catalog", headers=headers)
    assert allowed.status_code == 200
    denied = client.get(
        "/api/procurement/rules/effective?tenant_id=tenant-b&store_id=store-1",
        headers=headers,
    )
    assert denied.status_code == 403
    same_tenant_other_store = client.get(
        "/api/procurement/rules/effective?tenant_id=tenant-a&store_id=store-2",
        headers=headers,
    )
    assert same_tenant_other_store.status_code == 200


def test_platform_user_can_read_without_a_module_lookup(monkeypatch):
    def fail(user_id):
        raise AssertionError("platform users must not need a module lookup")

    monkeypatch.setattr(access, "load_module_codes", fail)
    response = client.get(
        "/api/procurement/rules/catalog",
        headers=_auth(_token(is_platform_user=True, role_names=["PLATFORM_OWNER"])),
    )
    assert response.status_code == 200


def test_unreadable_module_list_fails_closed(monkeypatch):
    def boom(user_id):
        raise RuntimeError("database offline")

    monkeypatch.setattr(access, "load_module_codes", boom)
    response = client.get("/api/procurement/rules/catalog", headers=_auth(_token()))
    assert response.status_code == 503
