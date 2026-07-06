"""Procurement Sprint 2 — Purchase Manager workflow tests (DB-free).

Covers workspace review, supplier assignment (single/bulk/change/remove),
export and every Module-7 validation, using stubs so no DB is opened.
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
    workspace_service, workspace_repository,
    assignment_service, assignment_repository,
    export_service, export_repository,
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
# Workspace review + Module 7 (quantity) validation
# ==========================================================================

def test_set_final_qty_rejects_negative(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: _item())
    with pytest.raises(HTTPException) as ei:
        workspace_service.set_final_qty("T1", "OI1", -5, None, "U1")
    assert ei.value.status_code == 400


def test_set_final_qty_not_below_assigned(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_item",
                        lambda t, o: _item(assigned_qty=40))
    with pytest.raises(HTTPException) as ei:
        workspace_service.set_final_qty("T1", "OI1", 30, None, "U1")
    assert ei.value.status_code == 409


def test_set_final_qty_ok(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: _item())
    monkeypatch.setattr(workspace_repository, "set_final_qty", lambda *a: 1)
    out = workspace_service.set_final_qty("T1", "OI1", 120, "more demand", "U1")
    assert out["order_item_id"] == "OI1"


def test_skip_requires_reason(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: _item())
    with pytest.raises(HTTPException) as ei:
        workspace_service.skip_item("T1", "OI1", "  ", "U1")
    assert ei.value.status_code == 400


def test_skip_blocked_when_assigned(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_item",
                        lambda t, o: _item(assigned_qty=10))
    with pytest.raises(HTTPException) as ei:
        workspace_service.skip_item("T1", "OI1", "discontinued", "U1")
    assert ei.value.status_code == 409


def test_restore_requires_skipped(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: _item())
    with pytest.raises(HTTPException) as ei:
        workspace_service.restore_item("T1", "OI1", "U1")
    assert ei.value.status_code == 409


# ==========================================================================
# Supplier assignment + Module 7 (assignment) validation
# ==========================================================================

def _patch_assign(monkeypatch, item, dup=False, already=0):
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: item)
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists",
                        lambda *a, **k: dup)
    monkeypatch.setattr(assignment_repository, "active_assigned_total",
                        lambda *a, **k: already)
    monkeypatch.setattr(assignment_repository, "insert_assignment",
                        lambda *a, **k: "A1")
    monkeypatch.setattr(assignment_repository, "recompute_order_item",
                        lambda *a, **k: None)
    monkeypatch.setattr(assignment_repository, "get_assignment",
                        lambda t, a: {"assignment_id": a, "supplier_code": "SUP1"})


def test_assign_zero_qty_rejected(monkeypatch):
    _patch_assign(monkeypatch, _item())
    with pytest.raises(HTTPException) as ei:
        assignment_service.assign_single("T1", "OI1", "SUP1", 0, None, "U1")
    assert ei.value.status_code == 400


def test_assign_exceeds_final_rejected(monkeypatch):
    _patch_assign(monkeypatch, _item(final_qty=100), already=80)
    with pytest.raises(HTTPException) as ei:
        assignment_service.assign_single("T1", "OI1", "SUP1", 30, None, "U1")
    assert ei.value.status_code == 409


def test_assign_duplicate_rejected(monkeypatch):
    _patch_assign(monkeypatch, _item(), dup=True)
    with pytest.raises(HTTPException) as ei:
        assignment_service.assign_single("T1", "OI1", "SUP1", 10, None, "U1")
    assert ei.value.status_code == 409


def test_assign_on_skipped_rejected(monkeypatch):
    _patch_assign(monkeypatch, _item(item_status="skipped"))
    with pytest.raises(HTTPException) as ei:
        assignment_service.assign_single("T1", "OI1", "SUP1", 10, None, "U1")
    assert ei.value.status_code == 409


def test_assign_single_ok(monkeypatch):
    _patch_assign(monkeypatch, _item(final_qty=100), already=0)
    out = assignment_service.assign_single("T1", "OI1", "SUP1", 40, "note", "U1")
    assert out["assignment"]["assignment_id"] == "A1"


def test_bulk_assign_reports_mixed(monkeypatch):
    items = {
        "OI1": _item(order_item_id="OI1", remaining_qty=50, final_qty=50),
        "OI2": _item(order_item_id="OI2", item_status="skipped"),
        "OI3": _item(order_item_id="OI3", remaining_qty=0, final_qty=10, assigned_qty=10),
    }
    monkeypatch.setattr(workspace_repository, "get_item", lambda t, o: items.get(o))
    monkeypatch.setattr(assignment_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(assignment_repository, "duplicate_active_exists",
                        lambda *a, **k: False)
    monkeypatch.setattr(assignment_repository, "active_assigned_total",
                        lambda c, t, o, **k: items[o].get("assigned_qty", 0))
    monkeypatch.setattr(assignment_repository, "insert_assignment", lambda *a, **k: "A")
    monkeypatch.setattr(assignment_repository, "recompute_order_item", lambda *a: None)

    out = assignment_service.assign_bulk(
        "T1", "SUP1",
        [{"order_item_id": "OI1"}, {"order_item_id": "OI2"}, {"order_item_id": "OI3"}],
        "U1",
    )
    assert out["assigned"] == 1        # OI1 only
    assert out["skipped"] == 2         # OI2 skipped, OI3 no remaining


def test_change_supplier_blocked_when_exported(monkeypatch):
    monkeypatch.setattr(assignment_repository, "get_assignment",
                        lambda t, a: {"assignment_id": a, "order_item_id": "OI1",
                                      "assignment_status": "exported"})
    with pytest.raises(HTTPException) as ei:
        assignment_service.change_supplier("T1", "A1", "SUP2", "U1")
    assert ei.value.status_code == 409


def test_remove_blocked_when_exported(monkeypatch):
    monkeypatch.setattr(assignment_repository, "get_assignment",
                        lambda t, a: {"assignment_id": a, "order_item_id": "OI1",
                                      "assignment_status": "exported"})
    with pytest.raises(HTTPException) as ei:
        assignment_service.remove_assignment("T1", "A1", "U1")
    assert ei.value.status_code == 409


# ==========================================================================
# Export + Module 7 (export) validation
# ==========================================================================

def test_export_requires_user():
    with pytest.raises(HTTPException) as ei:
        export_service.export_refresh("T1", "R1", None)
    assert ei.value.status_code == 403


def test_export_nothing_to_export(monkeypatch):
    monkeypatch.setattr(export_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(export_repository, "exportable_assignments",
                        lambda *a, **k: [])
    with pytest.raises(HTTPException) as ei:
        export_service.export_refresh("T1", "R1", "U1")
    assert ei.value.status_code == 400


def test_export_stamps_batch_and_splits_per_supplier(monkeypatch):
    rows = [
        {"assignment_id": "A1", "order_item_id": "OI1", "supplier_code": "SUP1",
         "assigned_qty": 10},
        {"assignment_id": "A2", "order_item_id": "OI2", "supplier_code": "SUP2",
         "assigned_qty": 20},
        {"assignment_id": "A3", "order_item_id": "OI3", "supplier_code": "SUP1",
         "assigned_qty": 5},
    ]
    marked = []
    monkeypatch.setattr(export_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(export_repository, "exportable_assignments",
                        lambda *a, **k: rows)

    def _mark(conn, tenant, aid, batch, split, uid, by):
        marked.append((aid, batch, split))
        return 1

    monkeypatch.setattr(export_repository, "mark_exported", _mark)

    out = export_service.export_refresh("T1", "R1", "U1")
    assert out["exported_count"] == 3
    assert out["supplier_count"] == 2
    batch = out["export_batch_number"]
    assert batch.startswith("EXP-")
    # every line stamped with the same batch; splits keyed by supplier
    assert all(m[1] == batch for m in marked)
    split_by_supplier = {"SUP1": marked[0][2], "SUP2": marked[1][2]}
    assert marked[2][2] == split_by_supplier["SUP1"]      # SUP1 shares its split
    assert split_by_supplier["SUP1"] != split_by_supplier["SUP2"]
