"""Procurement Sprint 3 tests (DB-free): GRN reconciliation, pending, next-
refresh comparison, cycle closing, decision explorer, and a stubbed end-to-end
walk of the post-export workflow.
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
    reconciliation_rules as recon_rules,
    reconciliation_service, reconciliation_repository,
    refresh_comparison,
    comparison_service, comparison_repository,
    pending_service, pending_repository,
    orchestration_service, repository as cycle_repo,
    workspace_service, workspace_repository,
)


class _FakeConn:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


# ==========================================================================
# Reconciliation rules (pure)
# ==========================================================================

def test_assignment_state():
    assert recon_rules.assignment_state(100, 0) == (100, recon_rules.EXPORTED)
    assert recon_rules.assignment_state(100, 100) == (0, recon_rules.RECEIVED)
    assert recon_rules.assignment_state(100, 60) == (40, recon_rules.PARTIAL_RECEIVED)
    # over-receipt does not create negative pending
    assert recon_rules.assignment_state(100, 120) == (0, recon_rules.RECEIVED)


def test_item_receipt_state():
    assert recon_rules.item_receipt_state(50, 50) == (0, recon_rules.ITEM_COMPLETED)
    assert recon_rules.item_receipt_state(50, 20) == (30, recon_rules.ITEM_PARTIAL)
    assert recon_rules.item_receipt_state(50, 0) == (50, recon_rules.ITEM_PENDING)


def test_match_receipts():
    a = {"product_code": "P1", "supplier_code": "S1"}
    receipts = [
        {"product_code": "P1", "supplier_code": "S1", "received_qty": 10, "grn_no": "G1", "supplier_bill_no": "B1"},
        {"product_code": "P1", "supplier_code": "S1", "received_qty": 5, "grn_no": "G2", "supplier_bill_no": None},
        {"product_code": "P2", "supplier_code": "S1", "received_qty": 99, "grn_no": "G9", "supplier_bill_no": "B9"},
    ]
    total, grn, bill = recon_rules.match_receipts(a, receipts)
    assert total == 15 and grn == "G2" and bill == "B1"


# ==========================================================================
# Next-refresh comparison (pure)
# ==========================================================================

def test_adjust_suggested():
    # completed with nothing fresh -> excluded (won't reappear)
    assert refresh_comparison.adjust_suggested(0, 0, False, True) == (False, 0)
    # carried pending re-procured on top of fresh baseline
    assert refresh_comparison.adjust_suggested(10, 20, True, False) == (True, 30)
    # fresh only
    assert refresh_comparison.adjust_suggested(15, 0, False, False) == (True, 15)


# ==========================================================================
# GRN submission + reconciliation service
# ==========================================================================

def test_submit_grn_requires_number():
    with pytest.raises(HTTPException) as ei:
        reconciliation_service.submit_grn("T1", "R1", "  ", "U1")
    assert ei.value.status_code == 400


def test_reconcile_matches_and_rolls_up(monkeypatch):
    monkeypatch.setattr(reconciliation_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(reconciliation_repository, "read_purchase_receipts",
                        lambda *a: [{"product_code": "P1", "supplier_code": "S1",
                                     "received_qty": 60, "grn_no": "G1",
                                     "supplier_bill_no": "B1"}])
    monkeypatch.setattr(reconciliation_repository, "exported_assignments",
                        lambda *a: [{"assignment_id": "A1", "order_item_id": "OI1",
                                     "product_code": "P1", "supplier_code": "S1",
                                     "assigned_qty": 100}])
    applied = {}
    monkeypatch.setattr(reconciliation_repository, "apply_receipt",
                        lambda c, t, aid, rec, rem, st, g, b: applied.update(
                            {"rec": rec, "rem": rem, "st": st}) or 1)
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh",
                        lambda *a: [{"order_item_id": "OI1", "final_qty": 100}])
    monkeypatch.setattr(reconciliation_repository, "item_received_total",
                        lambda *a: 60)
    item_set = {}
    monkeypatch.setattr(reconciliation_repository, "set_item_receipts",
                        lambda c, t, oid, rec, rem, st: item_set.update(
                            {"rec": rec, "rem": rem, "st": st}) or 1)

    out = reconciliation_service.reconcile("T1", "R1", "S1", "G1")
    assert applied == {"rec": 60, "rem": 40, "st": recon_rules.PARTIAL_RECEIVED}
    assert item_set == {"rec": 60, "rem": 40, "st": recon_rules.ITEM_PARTIAL}
    assert out["assignments_matched"] == 1
    assert out["items_partial"] == 1


# ==========================================================================
# Pending management
# ==========================================================================

def test_pending_adjust_rejects_negative(monkeypatch):
    monkeypatch.setattr(pending_repository, "get_item",
                        lambda t, o: {"order_item_id": o})
    with pytest.raises(HTTPException) as ei:
        pending_service.adjust("T1", "OI1", -1, "U1")
    assert ei.value.status_code == 400


def test_pending_carry_forward(monkeypatch):
    status = {}
    monkeypatch.setattr(pending_repository, "get_item",
                        lambda t, o: {"order_item_id": o, "pending_status": status.get("v")})
    monkeypatch.setattr(pending_repository, "set_pending_status",
                        lambda t, o, s, by: status.update({"v": s}) or 1)
    out = pending_service.carry_forward("T1", "OI1", "U1")
    assert status["v"] == "carried"
    assert out["pending_status"] == "carried"


def test_manual_add_validations(monkeypatch):
    monkeypatch.setattr(pending_repository, "product_already_in_refresh",
                        lambda t, r, p: True)
    with pytest.raises(HTTPException) as ei:
        pending_service.add_manual("T1", "R1", "C1", "S1", "PARA", "Para", 5, "U1")
    assert ei.value.status_code == 409

    monkeypatch.setattr(pending_repository, "product_already_in_refresh",
                        lambda t, r, p: False)
    with pytest.raises(HTTPException) as ei:
        pending_service.add_manual("T1", "R1", "C1", "S1", "PARA", "Para", 0, "U1")
    assert ei.value.status_code == 400

    monkeypatch.setattr(pending_repository, "add_manual_item",
                        lambda *a: "NEW-OI")
    out = pending_service.add_manual("T1", "R1", "C1", "S1", "PARA", "Para", 5, "U1")
    assert out["order_item_id"] == "NEW-OI" and out["is_manual"] is True


# ==========================================================================
# Carry-forward into the next refresh
# ==========================================================================

def test_carry_forward_seeds_next_refresh(monkeypatch):
    inserted = []
    monkeypatch.setattr(comparison_repository, "carried_pending",
                        lambda c, t, r: [
                            {"product_code": "P1", "product_id": "PID1", "remaining_qty": 20},
                            {"product_code": "P2", "product_id": "PID2", "remaining_qty": 0},
                        ])
    monkeypatch.setattr(comparison_repository, "exists_in_refresh",
                        lambda c, t, r, p: False)
    monkeypatch.setattr(comparison_repository, "insert_carried",
                        lambda c, t, ref, code, pid, qty, by: inserted.append((code, qty)) or 1)

    n = comparison_service.carry_forward(
        _FakeConn(), "T1", "R_PREV",
        {"refresh_id": "R2", "cycle_id": "C1", "store_id": "S1"}, "U1",
    )
    # P2 has 0 remaining -> excluded; only P1 carried
    assert n == 1
    assert inserted == [("P1", 20)]


def test_carry_forward_noop_without_previous():
    assert comparison_service.carry_forward(_FakeConn(), "T1", None, {}, "U1") == 0


# ==========================================================================
# Cycle closing
# ==========================================================================

def test_close_cycle_blocked_when_generating(monkeypatch):
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, "status": "ACTIVE"})
    monkeypatch.setattr(cycle_repo, "refreshing_in_progress", lambda t, c: True)
    with pytest.raises(HTTPException) as ei:
        orchestration_service.close_cycle("T1", "C1", "G9", "B9", "U1")
    assert ei.value.status_code == 409


def test_close_cycle_ok(monkeypatch):
    state = {"status": "ACTIVE"}
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, **state})
    monkeypatch.setattr(cycle_repo, "refreshing_in_progress", lambda t, c: False)

    def _close(t, c, g, b, by):
        state["status"] = "Closed"
        state["end_grn_number"] = g
        return 1

    monkeypatch.setattr(cycle_repo, "close_cycle", _close)
    out = orchestration_service.close_cycle("T1", "C1", "G9", "B9", "U1")
    assert out["status"] == "Closed" and out["end_grn_number"] == "G9"


def test_close_cycle_already_closed(monkeypatch):
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, "status": "Closed"})
    with pytest.raises(HTTPException) as ei:
        orchestration_service.close_cycle("T1", "C1", None, None, "U1")
    assert ei.value.status_code == 409


# ==========================================================================
# Decision Explorer
# ==========================================================================

def test_decision_explorer_returns_rules(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_decision",
                        lambda t, o: {"order_item_id": o, "reason_code": "INCLUDED_BELOW_MIN_DAYS",
                                      "effective_available_qty": 70, "final_qty": 130})
    out = workspace_service.get_decision("T1", "OI1")
    assert out["reason_code"] == "INCLUDED_BELOW_MIN_DAYS"
    assert any("PR-BR-009" in r for r in out["business_rules_applied"])


def test_decision_explorer_404(monkeypatch):
    monkeypatch.setattr(workspace_repository, "get_decision", lambda t, o: None)
    with pytest.raises(HTTPException) as ei:
        workspace_service.get_decision("T1", "OI1")
    assert ei.value.status_code == 404


# ==========================================================================
# End-to-end walk of the post-export workflow (stubbed persistence)
# ==========================================================================

def test_end_to_end_post_export(monkeypatch):
    """GRN submit -> reconcile -> pending carry-forward -> next refresh
    carry-forward -> close cycle. Verifies every stage returns success."""
    # GRN submit + reconcile (nothing synced yet -> zero, but flow completes)
    monkeypatch.setattr(reconciliation_repository, "get_refresh",
                        lambda t, r: {"refresh_id": r, "cycle_id": "C1", "store_id": "S1"})
    monkeypatch.setattr(reconciliation_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(reconciliation_repository, "store_last_grn", lambda *a: 1)
    monkeypatch.setattr(reconciliation_repository, "read_purchase_receipts", lambda *a: [])
    monkeypatch.setattr(reconciliation_repository, "exported_assignments", lambda *a: [])
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh", lambda *a: [])
    grn = reconciliation_service.submit_grn("T1", "R1", "4567", "U1")
    assert grn["last_grn_number"] == "4567"

    # pending carry-forward
    status = {}
    monkeypatch.setattr(pending_repository, "get_item",
                        lambda t, o: {"order_item_id": o, "pending_status": status.get("v")})
    monkeypatch.setattr(pending_repository, "set_pending_status",
                        lambda t, o, s, by: status.update({"v": s}) or 1)
    assert pending_service.carry_forward("T1", "OI1", "U1")["pending_status"] == "carried"

    # next-refresh carry-forward seeds pending
    monkeypatch.setattr(comparison_repository, "carried_pending",
                        lambda c, t, r: [{"product_code": "P1", "product_id": "PID1", "remaining_qty": 20}])
    monkeypatch.setattr(comparison_repository, "exists_in_refresh", lambda *a: False)
    monkeypatch.setattr(comparison_repository, "insert_carried", lambda *a: 1)
    assert comparison_service.carry_forward(
        _FakeConn(), "T1", "R1", {"refresh_id": "R2", "cycle_id": "C1", "store_id": "S1"}, "U1"
    ) == 1

    # close cycle (ACTIVE at validation, Closed after)
    cstate = {"status": "ACTIVE", "end_grn_number": None}
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, **cstate})
    monkeypatch.setattr(cycle_repo, "refreshing_in_progress", lambda t, c: False)

    def _close(t, c, g, b, by):
        cstate["status"] = "Closed"
        cstate["end_grn_number"] = g
        return 1

    monkeypatch.setattr(cycle_repo, "close_cycle", _close)
    closed = orchestration_service.close_cycle("T1", "C1", "4600", "88300", "U1")
    assert closed["status"] == "Closed" and closed["end_grn_number"] == "4600"
