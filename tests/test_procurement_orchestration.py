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
    vpl_history_repository,
    assignment_repository,
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

    monkeypatch.setattr(orch, "StoreRepository", lambda: _StoreOK())
    monkeypatch.setattr(
        cycle_repo, "get_cycle",
        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": "S1"},
    )
    monkeypatch.setattr(
        cycle_repo, "get_active_refresh_id", lambda t, c: "R_PREV"
    )
    monkeypatch.setattr(refresh_repo, "next_refresh_no", lambda t, c: 1)

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
    monkeypatch.setattr(items_repo, "carry_forward_skips", lambda *a, **k: 0)

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
    monkeypatch.setattr(refresh_repo, "get_vpl",
                         lambda t, r: {"snapshot_status": "Current"})

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


# --------------------------------------------------------------------------
# Step 4 — VPL History wiring (feature-gated, PROCUREMENT_VPL_HISTORY)
# --------------------------------------------------------------------------

def _stub_refresh_pipeline(monkeypatch, calls):
    monkeypatch.setattr(orch, "StoreRepository", lambda: _StoreOK())
    monkeypatch.setattr(
        cycle_repo, "get_cycle",
        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": "S1"},
    )
    monkeypatch.setattr(cycle_repo, "get_active_refresh_id", lambda t, c: "R_PREV")
    monkeypatch.setattr(refresh_repo, "next_refresh_no", lambda t, c: 1)
    monkeypatch.setattr(
        refresh_repo, "create_vpl",
        lambda data: {"refresh_id": "R_NEW", **data},
    )
    monkeypatch.setattr(
        decision_service, "generate_vpl",
        lambda t, r: {
            "status": "Ready", "generated_product_count": 1,
            "included_count": 1, "excluded_count": 0,
            "parameters": {"rolling_days": 90, "min_days": 10, "max_days": 20},
        },
    )
    monkeypatch.setattr(orch.comparison_service, "carry_forward", lambda *a: 0)
    monkeypatch.setattr(items_repo, "clear_working_items",
                         lambda *a: calls.append("clear_working_items") or 0)
    monkeypatch.setattr(items_repo, "generate_working_items",
                         lambda *a, **k: calls.append("generate_working_items") or 0)
    monkeypatch.setattr(items_repo, "carry_forward_skips", lambda *a, **k: 0)
    monkeypatch.setattr(refresh_repo, "set_status", lambda *a: None)
    monkeypatch.setattr(refresh_repo, "get_vpl",
                         lambda t, r: {"snapshot_status": "Current"})


def test_create_refresh_history_off_by_default(monkeypatch):
    """Default env (flag unset) never touches vpl_history_repository at all —
    matches D3c/D5's own default-off posture against the unapplied 0030."""
    calls = []
    monkeypatch.delenv("PROCUREMENT_VPL_HISTORY", raising=False)
    _stub_refresh_pipeline(monkeypatch, calls)
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        vpl_history_repository, "list_items_for_history",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")),
    )

    orch.create_refresh("T1", "C1", {"min_days": 10, "max_days": 20, "created_by": "U1"})
    assert calls == ["clear_working_items", "generate_working_items"]


def test_create_refresh_history_writes_batch_before_clearing(monkeypatch):
    """When enabled, the previous refresh's items+assignments are read and
    written to history BEFORE clear_working_items deletes them, on the same
    connection — proves the ordering, not just that both happened."""
    calls = []
    monkeypatch.setenv("PROCUREMENT_VPL_HISTORY", "1")
    _stub_refresh_pipeline(monkeypatch, calls)
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())

    lines = [{
        "order_item_id": "OI1", "product_id": "P1", "product_code": "100",
        "suggested_qty": 5, "final_qty": 5, "manual_override": False,
        "item_status": "draft", "skip_reason": None, "reviewed_by": None,
        "reviewed_at": None, "row_version": 1, "carried_forward": False,
    }]
    monkeypatch.setattr(
        vpl_history_repository, "list_items_for_history",
        lambda conn, t, r: calls.append(("list_items_for_history", r)) or lines,
    )
    monkeypatch.setattr(
        assignment_repository, "list_by_refresh",
        lambda t, r: calls.append(("list_by_refresh", r)) or [
            {"order_item_id": "OI1", "assignment_id": "A1",
             "supplier_code": "SUP1", "assigned_qty": 5, "assignment_status": "assigned"}
        ],
    )

    written = {}

    def _write(conn, tenant_id, store_id, cycle_id, source_refresh_id,
               successor_refresh_id, lines_arg, assignments_by_item, created_by,
               rule_snapshot_id=None):
        calls.append("write_history_batch")
        written.update(
            tenant_id=tenant_id, store_id=store_id, cycle_id=cycle_id,
            source_refresh_id=source_refresh_id, successor_refresh_id=successor_refresh_id,
            lines=lines_arg, assignments_by_item=assignments_by_item,
        )
        return "H1"

    monkeypatch.setattr(vpl_history_repository, "write_history_batch", _write)

    orch.create_refresh("T1", "C1", {"min_days": 10, "max_days": 20, "created_by": "U1"})

    assert calls == [
        ("list_items_for_history", "R_PREV"),
        ("list_by_refresh", "R_PREV"),
        "write_history_batch",
        "clear_working_items",
        "generate_working_items",
    ]
    assert written["tenant_id"] == "T1"
    assert written["store_id"] == "S1"
    assert written["source_refresh_id"] == "R_PREV"
    assert written["successor_refresh_id"] == "R_NEW"
    assert written["lines"] == lines
    assert written["assignments_by_item"] == {"OI1": [
        {"order_item_id": "OI1", "assignment_id": "A1", "supplier_code": "SUP1",
         "assigned_qty": 5, "assignment_status": "assigned"}
    ]}


def test_create_refresh_history_skips_write_when_no_previous_items(monkeypatch):
    """First refresh in a cycle (no previous_refresh_id) or a previous refresh
    with zero items never calls write_history_batch — nothing to archive."""
    calls = []
    monkeypatch.setenv("PROCUREMENT_VPL_HISTORY", "1")
    _stub_refresh_pipeline(monkeypatch, calls)
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(cycle_repo, "get_active_refresh_id", lambda t, c: None)
    monkeypatch.setattr(
        vpl_history_repository, "list_items_for_history",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")),
    )
    monkeypatch.setattr(
        vpl_history_repository, "write_history_batch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")),
    )

    orch.create_refresh("T1", "C1", {"min_days": 10, "max_days": 20, "created_by": "U1"})
    assert calls == ["clear_working_items", "generate_working_items"]


def test_create_refresh_history_failure_rolls_back_before_clearing(monkeypatch):
    """A forced failure in write_history_batch must roll back the shared
    connection and must never reach clear_working_items — proves the previous
    refresh's items survive intact when the history write fails, instead of
    being deleted with no corresponding history batch."""
    calls = []
    monkeypatch.setenv("PROCUREMENT_VPL_HISTORY", "1")
    _stub_refresh_pipeline(monkeypatch, calls)

    class _TrackingConn(_FakeConn):
        def __init__(self):
            self.rolled_back = False
            self.committed = False

        def rollback(self):
            self.rolled_back = True

        def commit(self):
            self.committed = True

    conn_holder = {}

    def _get_conn():
        conn_holder["conn"] = _TrackingConn()
        return conn_holder["conn"]

    monkeypatch.setattr(orch, "get_connection", _get_conn)
    monkeypatch.setattr(
        vpl_history_repository, "list_items_for_history",
        lambda conn, t, r: [{"order_item_id": "OI1", "product_id": "P1"}],
    )
    monkeypatch.setattr(assignment_repository, "list_by_refresh", lambda t, r: [])

    class _Boom(Exception):
        pass

    def _write(*a, **k):
        raise _Boom("forced failure")

    monkeypatch.setattr(vpl_history_repository, "write_history_batch", _write)

    with pytest.raises(_Boom):
        orch.create_refresh("T1", "C1", {"min_days": 10, "max_days": 20, "created_by": "U1"})

    assert "clear_working_items" not in calls
    assert "generate_working_items" not in calls
    assert conn_holder["conn"].rolled_back is True
    assert conn_holder["conn"].committed is False


def test_create_refresh_history_retry_is_idempotent_on_unique_violation(monkeypatch):
    """A duplicate-batch unique-index violation (the retry-safety case
    vpl_history_repository.write_history_batch documents) is swallowed, not
    raised — the refresh still completes instead of 500ing on a retry."""
    calls = []
    monkeypatch.setenv("PROCUREMENT_VPL_HISTORY", "1")
    _stub_refresh_pipeline(monkeypatch, calls)
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        vpl_history_repository, "list_items_for_history",
        lambda conn, t, r: [{"order_item_id": "OI1", "product_id": "P1"}],
    )
    monkeypatch.setattr(assignment_repository, "list_by_refresh", lambda t, r: [])

    class _IntegrityError(Exception):
        pass

    def _write(*a, **k):
        raise _IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(vpl_history_repository, "write_history_batch", _write)

    orch.create_refresh("T1", "C1", {"min_days": 10, "max_days": 20, "created_by": "U1"})
    assert calls == ["clear_working_items", "generate_working_items"]


def test_create_refresh_validates_parameters(monkeypatch):
    monkeypatch.setattr(
        cycle_repo, "get_cycle",
        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": None},
    )
    with pytest.raises(HTTPException) as ei:
        orch.create_refresh("T1", "C1", {"min_days": 20, "max_days": 10})
    assert ei.value.status_code == 400
