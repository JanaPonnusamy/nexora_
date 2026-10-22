"""Step 3 — concurrency/transaction safeguards (DB-free).

D4: lock_order_item_for_assignment serializes the assign_single/assign_bulk
check-then-insert (TOCTOU fix, Audit D item 2 in PHASE_2_CLAUDE_REVIEW.md).
D5: create_refresh returns/reuses the existing result for a retried request
carrying the same idempotency_key, feature-gated behind
PROCUREMENT_REFRESH_IDEMPOTENCY (0029_refresh_idempotency_key.sql not applied).
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from fastapi import HTTPException  # noqa: E402
from modules.procurement import (  # noqa: E402
    assignment_service, assignment_repository,
    workspace_repository,
    orchestration_service as orch,
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


def _item(**over):
    base = {
        "order_item_id": "OI1", "tenant_id": "T1", "cycle_id": "C1",
        "refresh_id": "R1", "store_id": "S1", "product_id": "P1",
        "product_code": "PARA-500", "suggested_qty": 100, "final_qty": 100,
        "assigned_qty": 0, "remaining_qty": 100, "item_status": "draft",
    }
    base.update(over)
    return base


# ==========================================================================
# D4 — lock_order_item_for_assignment is called before the check-then-insert
# ==========================================================================

def test_assign_single_locks_the_order_item_before_checking(monkeypatch):
    calls = []
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: _item())
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "lock_order_item_for_assignment",
                         lambda *a, **k: calls.append("lock"))
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists",
                         lambda *a, **k: calls.append("dup_check") or False)
    monkeypatch.setattr(assignment_repository, "any_active_assignment",
                         lambda *a, **k: calls.append("active_check") or None)
    monkeypatch.setattr(assignment_repository, "active_assigned_total", lambda *a, **k: 0)
    monkeypatch.setattr(assignment_repository, "insert_assignment", lambda *a, **k: "A1")
    monkeypatch.setattr(assignment_repository, "recompute_order_item", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "get_assignment",
                         lambda t, a: {"assignment_id": a, "supplier_code": "SUP1"})

    assignment_service.assign_single("T1", "OI1", "SUP1", 10, None, "U1")
    assert calls == ["lock", "dup_check", "active_check"]


def test_assign_bulk_locks_each_order_item_before_checking(monkeypatch):
    calls = []
    items = {"OI1": _item(order_item_id="OI1")}
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: items.get(o))
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "lock_order_item_for_assignment",
                         lambda *a, **k: calls.append("lock"))
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists", lambda *a, **k: False)
    monkeypatch.setattr(assignment_repository, "any_active_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "active_assigned_total", lambda *a, **k: 0)
    monkeypatch.setattr(assignment_repository, "insert_assignment", lambda *a, **k: "A")
    monkeypatch.setattr(assignment_repository, "recompute_order_item", lambda *a: None)

    out = assignment_service.assign_bulk("T1", "SUP1", [{"order_item_id": "OI1"}], "U1")
    assert out["assigned"] == 1
    assert calls == ["lock"]


def test_lock_order_item_for_assignment_uses_updlock_holdlock():
    captured = {}

    class _Cursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self):
            return ("OI1",)

    class _Conn:
        def cursor(self):
            return _Cursor()

    row = assignment_repository.lock_order_item_for_assignment(_Conn(), "T1", "OI1")
    assert row is not None
    assert "UPDLOCK" in captured["sql"] and "HOLDLOCK" in captured["sql"]
    assert captured["params"] == ("T1", "OI1")


# ==========================================================================
# D5 — refresh retry idempotency (flag-gated)
# ==========================================================================

@pytest.fixture(autouse=True)
def _reset_flag(monkeypatch):
    monkeypatch.delenv("PROCUREMENT_REFRESH_IDEMPOTENCY", raising=False)
    yield


class _StoreOK:
    def get_by_id(self, sid):
        return ("row",)


def _patch_cycle(monkeypatch, cycle_id="C1", store_id="S1"):
    monkeypatch.setattr(
        cycle_repo, "get_cycle",
        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": store_id},
    )
    monkeypatch.setattr(cycle_repo, "get_active_refresh_id", lambda t, c: None)
    monkeypatch.setattr(refresh_repo, "next_refresh_no", lambda t, c: 1)
    monkeypatch.setattr(orch, "StoreRepository", lambda: _StoreOK())


def test_idempotency_key_ignored_when_flag_off(monkeypatch):
    _patch_cycle(monkeypatch)
    lookups = []
    monkeypatch.setattr(refresh_repo, "find_by_idempotency_key",
                         lambda *a, **k: lookups.append(1) or {"refresh_id": "SHOULD_NOT_BE_USED"})
    monkeypatch.setattr(refresh_repo, "create_vpl",
                         lambda data: {"refresh_id": "R_NEW", **data})
    monkeypatch.setattr(decision_service, "generate_vpl", lambda t, r: {
        "status": "Ready", "generated_product_count": 1,
        "included_count": 1, "excluded_count": 0,
        "parameters": {"rolling_days": 90, "min_days": 10, "max_days": 20},
    })
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(orch.comparison_service, "carry_forward", lambda *a: 0)
    monkeypatch.setattr(items_repo, "clear_working_items", lambda *a: 0)
    monkeypatch.setattr(items_repo, "generate_working_items", lambda *a, **k: 0)
    monkeypatch.setattr(items_repo, "carry_forward_skips", lambda *a, **k: None)
    monkeypatch.setattr(refresh_repo, "set_status", lambda *a, **k: None)

    out = orch.create_refresh("T1", "C1", {
        "min_days": 10, "max_days": 20, "created_by": "U1",
        "idempotency_key": "retry-key-1",
    })
    assert lookups == []  # lookup never attempted — flag is off
    assert out["refresh_id"] == "R_NEW"


def test_idempotency_hit_returns_existing_refresh_without_creating_a_new_one(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_REFRESH_IDEMPOTENCY", "1")
    _patch_cycle(monkeypatch)
    monkeypatch.setattr(
        refresh_repo, "find_by_idempotency_key",
        lambda t, c, k: {"refresh_id": "R_EXISTING"} if k == "retry-key-1" else None,
    )

    def _create_vpl(data):
        raise AssertionError("create_vpl must not be called on an idempotency hit")

    monkeypatch.setattr(refresh_repo, "create_vpl", _create_vpl)

    out = orch.create_refresh("T1", "C1", {
        "min_days": 10, "max_days": 20, "created_by": "U1",
        "idempotency_key": "retry-key-1",
    })
    assert out == {"refresh_id": "R_EXISTING"}


def test_idempotency_miss_creates_a_new_refresh_with_the_key_stored(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_REFRESH_IDEMPOTENCY", "1")
    _patch_cycle(monkeypatch)
    monkeypatch.setattr(refresh_repo, "find_by_idempotency_key", lambda *a, **k: None)

    captured = {}

    def _create_vpl(data):
        captured.update(data)
        return {"refresh_id": "R_NEW", **data}

    monkeypatch.setattr(refresh_repo, "create_vpl", _create_vpl)
    monkeypatch.setattr(decision_service, "generate_vpl", lambda t, r: {
        "status": "Ready", "generated_product_count": 1,
        "included_count": 1, "excluded_count": 0,
        "parameters": {"rolling_days": 90, "min_days": 10, "max_days": 20},
    })
    monkeypatch.setattr(orch, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(orch.comparison_service, "carry_forward", lambda *a: 0)
    monkeypatch.setattr(items_repo, "clear_working_items", lambda *a: 0)
    monkeypatch.setattr(items_repo, "generate_working_items", lambda *a, **k: 0)
    monkeypatch.setattr(items_repo, "carry_forward_skips", lambda *a, **k: None)
    monkeypatch.setattr(refresh_repo, "set_status", lambda *a, **k: None)

    out = orch.create_refresh("T1", "C1", {
        "min_days": 10, "max_days": 20, "created_by": "U1",
        "idempotency_key": "retry-key-2",
    })
    assert captured["idempotency_key"] == "retry-key-2"
    assert out["refresh_id"] == "R_NEW"


def test_concurrent_retry_unique_violation_falls_back_to_existing_row(monkeypatch):
    """Both callers miss find_by_idempotency_key (neither has committed yet);
    the first wins the real INSERT, the second's create_vpl raises a unique-
    constraint violation (simulated) and must recover by re-reading the
    winner's row instead of propagating a 500."""
    monkeypatch.setenv("PROCUREMENT_REFRESH_IDEMPOTENCY", "1")
    _patch_cycle(monkeypatch)

    class IntegrityError(Exception):
        pass

    calls = {"lookup": 0}

    def _find(t, c, k):
        calls["lookup"] += 1
        if calls["lookup"] == 1:
            return None  # first check: miss
        return {"refresh_id": "R_WINNER"}  # second check, after the race: hit

    monkeypatch.setattr(refresh_repo, "find_by_idempotency_key", _find)

    def _create_vpl(data):
        raise IntegrityError("Violation of UNIQUE KEY constraint")

    monkeypatch.setattr(refresh_repo, "create_vpl", _create_vpl)

    out = orch.create_refresh("T1", "C1", {
        "min_days": 10, "max_days": 20, "created_by": "U1",
        "idempotency_key": "race-key",
    })
    assert out == {"refresh_id": "R_WINNER"}
    assert calls["lookup"] == 2


def test_non_idempotency_exception_still_propagates(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_REFRESH_IDEMPOTENCY", "1")
    _patch_cycle(monkeypatch)
    monkeypatch.setattr(refresh_repo, "find_by_idempotency_key", lambda *a, **k: None)

    def _create_vpl(data):
        raise RuntimeError("unrelated database error")

    monkeypatch.setattr(refresh_repo, "create_vpl", _create_vpl)

    with pytest.raises(RuntimeError):
        orch.create_refresh("T1", "C1", {
            "min_days": 10, "max_days": 20, "created_by": "U1",
            "idempotency_key": "some-key",
        })
