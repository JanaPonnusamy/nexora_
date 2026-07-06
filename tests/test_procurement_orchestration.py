"""Procurement Phase 4 — lifecycle orchestration tests (DB-free).

Unit-tests the cycle/refresh validation guards and integration-tests the full
Refresh pipeline (create -> engine -> working items -> publish) with stubs, so
no database connection is opened.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from fastapi import HTTPException  # noqa: E402
from modules.procurement import orchestration_service as orch  # noqa: E402
from modules.procurement import (  # noqa: E402
    repository as cycle_repo,
    vpl_repository as refresh_repo,
    order_items_repository as items_repo,
    decision_service,
)


class _FakeConn:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


# --------------------------------------------------------------------------
# Cycle open — validation guards
# --------------------------------------------------------------------------

def test_open_cycle_requires_user(monkeypatch):
    with pytest.raises(HTTPException) as ei:
        orch.create_business_cycle({"tenant_id": "T1", "name": "C"})
    assert ei.value.status_code == 403


def test_open_cycle_blocks_when_active_exists(monkeypatch):
    monkeypatch.setattr(orch, "StoreRepository", lambda: _StoreOK())
    monkeypatch.setattr(cycle_repo, "active_cycle_exists", lambda t, s=None: True)
    with pytest.raises(HTTPException) as ei:
        orch.create_business_cycle(
            {"tenant_id": "T1", "name": "C", "store_id": "S1", "created_by": "U1"}
        )
    assert ei.value.status_code == 409


def test_open_cycle_rejects_missing_store(monkeypatch):
    monkeypatch.setattr(orch, "StoreRepository", lambda: _StoreMissing())
    with pytest.raises(HTTPException) as ei:
        orch.create_business_cycle(
            {"tenant_id": "T1", "name": "C", "store_id": "BAD", "created_by": "U1"}
        )
    assert ei.value.status_code == 400


def test_open_cycle_creates_active(monkeypatch):
    captured = {}
    monkeypatch.setattr(orch, "StoreRepository", lambda: _StoreOK())
    monkeypatch.setattr(cycle_repo, "active_cycle_exists", lambda t, s=None: False)

    def _create(data):
        captured.update(data)
        return {"cycle_id": "C1", **data}

    monkeypatch.setattr(cycle_repo, "create_cycle", _create)
    out = orch.create_business_cycle({
        "tenant_id": "T1", "name": "Cycle", "store_id": "S1",
        "start_grn_number": "G100", "start_sale_bill_number": "S100",
        "created_by": "U1",
    })
    assert out["cycle_id"] == "C1"
    assert captured["status"] == "ACTIVE"
    assert captured["start_grn_number"] == "G100"


class _StoreOK:
    def get_by_id(self, sid):
        return ("row",)


class _StoreMissing:
    def get_by_id(self, sid):
        return None


# --------------------------------------------------------------------------
# Refresh orchestration — integration (stubbed persistence)
# --------------------------------------------------------------------------

def test_create_refresh_requires_active_cycle(monkeypatch):
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, "status": "DRAFT"})
    with pytest.raises(HTTPException) as ei:
        orch.create_refresh("T1", "C1", {"min_days": 10, "max_days": 20})
    assert ei.value.status_code == 409


def test_create_refresh_full_pipeline(monkeypatch):
    calls = []

    monkeypatch.setattr(
        cycle_repo, "get_cycle",
        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": "S1"},
    )
    monkeypatch.setattr(
        cycle_repo, "get_active_refresh_id", lambda t, c: "R_PREV"
    )

    def _create_vpl(data):
        calls.append("create_refresh")
        assert data["min_days"] == 10 and data["max_days"] == 20
        assert data["previous_refresh_id"] == "R_PREV"
        assert data["store_id"] == "S1"
        return {"refresh_id": "R_NEW", **data}

    monkeypatch.setattr(refresh_repo, "create_vpl", _create_vpl)

    def _engine(t, r):
        calls.append("engine")
        assert r == "R_NEW"
        return {
            "status": "Ready", "generated_product_count": 12,
            "included_count": 5, "excluded_count": 7,
            "parameters": {"rolling_days": 90, "min_days": 10, "max_days": 20},
        }

    monkeypatch.setattr(decision_service, "generate_vpl", _engine)
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(orch.comparison_service, "carry_forward", lambda *a: 0)
    monkeypatch.setattr(items_repo, "clear_working_items", lambda *a: 0)

    def _gen_items(conn, t, r, store_id, created_by):
        calls.append("working_items")
        assert r == "R_NEW" and store_id == "S1"
        return 5

    monkeypatch.setattr(items_repo, "generate_working_items", _gen_items)

    archived = {}

    def _set_status(t, r, status, by):
        archived["refresh"] = r
        archived["status"] = status

    monkeypatch.setattr(refresh_repo, "set_status", _set_status)

    result = orch.create_refresh("T1", "C1", {
        "min_days": 10, "max_days": 20, "created_by": "U1",
    })

    # ordered pipeline: refresh created -> engine -> working items
    assert calls == ["create_refresh", "engine", "working_items"]
    assert result["refresh_id"] == "R_NEW"
    assert result["working_item_count"] == 5
    assert result["generated_product_count"] == 12
    assert result["previous_refresh_id"] == "R_PREV"
    # previous CURRENT refresh archived
    assert archived == {"refresh": "R_PREV", "status": "Archived"}


def test_create_refresh_validates_parameters(monkeypatch):
    monkeypatch.setattr(
        cycle_repo, "get_cycle",
        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": None},
    )
    with pytest.raises(HTTPException) as ei:
        orch.create_refresh("T1", "C1", {"min_days": 20, "max_days": 10})
    assert ei.value.status_code == 400
