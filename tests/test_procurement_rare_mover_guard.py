"""D3c — rare-mover confirmation enforcement (DB-free).

Owner decision (2026-10-21): discrete rare_confirmed field, scoped to the
current cycle by construction (each cycle/refresh mints a fresh order_item
row). Enforcement is feature-gated behind PROCUREMENT_RARE_MOVER_ENFORCEMENT
(default off) because migration 0028_rare_mover_confirmation.sql, which adds
the column, is NOT applied — see rare_mover_guard.py's module docstring.
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
    rare_mover_guard,
    assignment_service, assignment_repository,
    export_service, export_repository,
    workspace_repository,
)
from modules.procurement.decision_rules import INCLUDED_RARE_MOVER_TOPUP  # noqa: E402


class _FakeConn:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _rare_item(**over):
    base = {
        "order_item_id": "OI1", "tenant_id": "T1", "cycle_id": "C1",
        "refresh_id": "R1", "store_id": "S1", "product_id": "P1",
        "product_code": "RARE-1", "suggested_qty": 1, "final_qty": 1,
        "assigned_qty": 0, "remaining_qty": 1, "item_status": "draft",
        "reason_code": INCLUDED_RARE_MOVER_TOPUP, "rare_confirmed": False,
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _reset_flag(monkeypatch):
    monkeypatch.delenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", raising=False)
    yield


# ==========================================================================
# Guard unit behavior
# ==========================================================================

def test_enforcement_off_by_default():
    assert rare_mover_guard.enforcement_enabled() is False


def test_require_confirmed_noop_when_flag_off():
    # Flag off: even an unconfirmed rare-mover item passes.
    rare_mover_guard.require_confirmed(_rare_item(rare_confirmed=False))


def test_require_confirmed_noop_for_non_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    rare_mover_guard.require_confirmed(_rare_item(reason_code="SOMETHING_ELSE"))


def test_require_confirmed_blocks_unconfirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    with pytest.raises(HTTPException) as ei:
        rare_mover_guard.require_confirmed(_rare_item(rare_confirmed=False))
    assert ei.value.status_code == 409


def test_require_confirmed_allows_confirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    rare_mover_guard.require_confirmed(_rare_item(rare_confirmed=True))


# ==========================================================================
# assign_single
# ==========================================================================

def _patch_assign(monkeypatch, item):
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: item)
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "lock_order_item_for_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists", lambda *a, **k: False)
    monkeypatch.setattr(assignment_repository, "any_active_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "active_assigned_total", lambda *a, **k: 0)
    monkeypatch.setattr(assignment_repository, "insert_assignment", lambda *a, **k: "A1")
    monkeypatch.setattr(assignment_repository, "recompute_order_item", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "get_assignment",
                         lambda t, a: {"assignment_id": a, "supplier_code": "SUP1"})


def test_assign_single_rejects_unconfirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    _patch_assign(monkeypatch, _rare_item(rare_confirmed=False))
    with pytest.raises(HTTPException) as ei:
        assignment_service.assign_single("T1", "OI1", "SUP1", 1, None, "U1")
    assert ei.value.status_code == 409


def test_assign_single_allows_confirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    _patch_assign(monkeypatch, _rare_item(rare_confirmed=True))
    out = assignment_service.assign_single("T1", "OI1", "SUP1", 1, None, "U1")
    assert out["assignment"]["assignment_id"] == "A1"


def test_assign_single_rare_mover_ignored_when_flag_off(monkeypatch):
    _patch_assign(monkeypatch, _rare_item(rare_confirmed=False))
    out = assignment_service.assign_single("T1", "OI1", "SUP1", 1, None, "U1")
    assert out["assignment"]["assignment_id"] == "A1"


# ==========================================================================
# assign_bulk — per-item isolation
# ==========================================================================

def test_bulk_assign_isolates_unconfirmed_rare_mover_without_blocking_the_rest(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    items = {
        "OI1": _rare_item(order_item_id="OI1", rare_confirmed=False),
        "OI2": {
            "order_item_id": "OI2", "item_status": "draft", "final_qty": 50,
            "remaining_qty": 50, "assigned_qty": 0, "reason_code": "OTHER",
        },
    }
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: items.get(o))
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "lock_order_item_for_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists", lambda *a, **k: False)
    monkeypatch.setattr(assignment_repository, "any_active_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "active_assigned_total", lambda *a, **k: 0)
    monkeypatch.setattr(assignment_repository, "insert_assignment", lambda *a, **k: "A")
    monkeypatch.setattr(assignment_repository, "recompute_order_item", lambda *a: None)

    out = assignment_service.assign_bulk(
        "T1", "SUP1", [{"order_item_id": "OI1"}, {"order_item_id": "OI2"}], "U1",
    )
    assert out["assigned"] == 1
    assert out["skipped"] == 1
    skipped_reasons = {r["order_item_id"]: r["reason"] for r in out["results"] if r["status"] == "skipped"}
    assert "confirmation" in skipped_reasons["OI1"]


def test_bulk_assign_allows_confirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    items = {"OI1": _rare_item(order_item_id="OI1", rare_confirmed=True)}
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: items.get(o))
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "lock_order_item_for_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists", lambda *a, **k: False)
    monkeypatch.setattr(assignment_repository, "any_active_assignment", lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "active_assigned_total", lambda *a, **k: 0)
    monkeypatch.setattr(assignment_repository, "insert_assignment", lambda *a, **k: "A")
    monkeypatch.setattr(assignment_repository, "recompute_order_item", lambda *a: None)

    out = assignment_service.assign_bulk("T1", "SUP1", [{"order_item_id": "OI1"}], "U1")
    assert out["assigned"] == 1


# ==========================================================================
# export_refresh — fails closed for the whole batch
# ==========================================================================

def test_export_rejects_batch_containing_unconfirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    rows = [
        {"assignment_id": "A1", "order_item_id": "OI1", "supplier_code": "SUP1",
         "assigned_qty": 10, "reason_code": INCLUDED_RARE_MOVER_TOPUP, "rare_confirmed": False},
        {"assignment_id": "A2", "order_item_id": "OI2", "supplier_code": "SUP2",
         "assigned_qty": 20, "reason_code": "OTHER", "rare_confirmed": False},
    ]
    monkeypatch.setattr(export_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(export_repository, "exportable_assignments", lambda *a, **k: rows)
    with pytest.raises(HTTPException) as ei:
        export_service.export_refresh("T1", "R1", "U1")
    assert ei.value.status_code == 409


def test_export_allows_batch_with_confirmed_rare_mover(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    rows = [
        {"assignment_id": "A1", "order_item_id": "OI1", "supplier_code": "SUP1",
         "assigned_qty": 10, "reason_code": INCLUDED_RARE_MOVER_TOPUP, "rare_confirmed": True},
    ]
    monkeypatch.setattr(export_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(export_repository, "exportable_assignments", lambda *a, **k: rows)
    monkeypatch.setattr(export_repository, "mark_exported", lambda *a, **k: 1)
    out = export_service.export_refresh("T1", "R1", "U1")
    assert out["exported_count"] == 1


def test_export_rare_mover_ignored_when_flag_off(monkeypatch):
    rows = [
        {"assignment_id": "A1", "order_item_id": "OI1", "supplier_code": "SUP1",
         "assigned_qty": 10, "reason_code": INCLUDED_RARE_MOVER_TOPUP, "rare_confirmed": False},
    ]
    monkeypatch.setattr(export_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(export_repository, "exportable_assignments", lambda *a, **k: rows)
    monkeypatch.setattr(export_repository, "mark_exported", lambda *a, **k: 1)
    out = export_service.export_refresh("T1", "R1", "U1")
    assert out["exported_count"] == 1


# ==========================================================================
# Cross-tenant / cycle-scoping — confirmation lives on the order_item row,
# which is itself tenant- and cycle-scoped (new refresh = new row, D3/D6).
# ==========================================================================

def test_confirmation_is_per_row_not_a_global_flag(monkeypatch):
    """Two order_items for the same product_code in different cycles never
    share a rare_confirmed value — each is read independently via get_item."""
    monkeypatch.setenv("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "1")
    cycle_1 = _rare_item(order_item_id="OI1", cycle_id="C1", rare_confirmed=True)
    cycle_2 = _rare_item(order_item_id="OI2", cycle_id="C2", rare_confirmed=False)
    rare_mover_guard.require_confirmed(cycle_1)
    with pytest.raises(HTTPException):
        rare_mover_guard.require_confirmed(cycle_2)


def test_confirm_rare_mover_repository_call_shape(monkeypatch):
    calls = []
    monkeypatch.setattr(
        workspace_repository, "_run",
        lambda sql, params: calls.append(params) or 1,
    )
    affected = workspace_repository.confirm_rare_mover("T1", "OI1", "11111111-1111-1111-1111-111111111111")
    assert affected == 1
    assert calls[0][-2:] == ("T1", "OI1")
