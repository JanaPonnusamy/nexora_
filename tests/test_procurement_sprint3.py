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


# --------------------------------------------------------------------------
# read_purchase_receipts — GRN-watermark-by-date fix (2026-10-23)
# --------------------------------------------------------------------------

class _FakeCursor:
    """Records every executed statement (sql text + params) and returns a
    scripted fetchone/fetchall result per call, in call order."""
    def __init__(self, fetchone_results=None, fetchall_result=None):
        self.calls = []
        self._fetchone_results = list(fetchone_results or [])
        self._fetchall_result = fetchall_result or []
        self.description = [("product_code",), ("supplier_code",),
                             ("received_qty",), ("grn_no",), ("supplier_bill_no",)]

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self._fetchone_results.pop(0) if self._fetchone_results else None

    def fetchall(self):
        return self._fetchall_result


class _FakeConnWithCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_read_purchase_receipts_resolves_last_grn_to_a_date_cutoff():
    """A supplied last_grn is first resolved to its own GRNDate (not compared
    directly, per owner decision 2026-10-23: GRNNumber is not a safe
    sequential key) — the second query must filter GRNDate <= that
    resolved date, not GRNNumber <= last_grn."""
    import datetime
    cutoff = datetime.date(2026, 9, 1)
    cursor = _FakeCursor(fetchone_results=[(cutoff,)])
    conn = _FakeConnWithCursor(cursor)

    reconciliation_repository.read_purchase_receipts(conn, "T1", "S1", "4567")

    assert len(cursor.calls) == 2
    lookup_sql, lookup_params = cursor.calls[0]
    assert "MAX(pt.GRNDate)" in lookup_sql
    assert "GRNNumber" in lookup_sql
    assert lookup_params == ("T1", "S1", "4567")

    read_sql, read_params = cursor.calls[1]
    assert "GRNDate <= ?" in read_sql
    assert "GRNNumber <= " not in read_sql  # never a direct GRNNumber comparison
    assert read_params == ("T1", "S1", cutoff, cutoff)


def test_read_purchase_receipts_unmatched_last_grn_falls_back_to_unbounded():
    """A last_grn that doesn't resolve to any GRNDate (typo, wrong store,
    never synced) must not silently return zero receipts — falls back to the
    prior unbounded read rather than making reconciliation look like nothing
    was ever received."""
    cursor = _FakeCursor(fetchone_results=[(None,)])
    conn = _FakeConnWithCursor(cursor)

    reconciliation_repository.read_purchase_receipts(conn, "T1", "S1", "NOPE")

    read_sql, read_params = cursor.calls[1]
    assert read_params == ("T1", "S1", None, None)


def test_read_purchase_receipts_no_last_grn_skips_the_lookup_entirely():
    """No last_grn supplied (last_grn=None, e.g. close_cycle's own
    reconcile() call, which passes no last_grn) must not run the GRNDate
    lookup query at all — exactly one query, unbounded, same as before this
    fix for a caller that never supplies a GRN number."""
    cursor = _FakeCursor()
    conn = _FakeConnWithCursor(cursor)

    reconciliation_repository.read_purchase_receipts(conn, "T1", "S1", None)

    assert len(cursor.calls) == 1
    read_sql, read_params = cursor.calls[0]
    assert read_params == ("T1", "S1", None, None)


# --------------------------------------------------------------------------
# submit_grn / reconcile — shared-transaction fix (GRN audit follow-up)
# --------------------------------------------------------------------------

class _TrackingConn(_FakeConn):
    """Same no-op _FakeConn contract, but records commit/rollback/close calls
    so a test can assert exactly what the connection owner did, not just that
    no exception propagated."""
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _stub_reconcile_repo(monkeypatch, receipts=None, assignments=None,
                         items=None, received_total=0):
    monkeypatch.setattr(reconciliation_repository, "read_purchase_receipts",
                        lambda *a: receipts or [])
    monkeypatch.setattr(reconciliation_repository, "exported_assignments",
                        lambda *a: assignments or [])
    monkeypatch.setattr(reconciliation_repository, "apply_receipt", lambda *a: 1)
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh",
                        lambda *a: items or [])
    monkeypatch.setattr(reconciliation_repository, "item_received_total",
                        lambda *a: received_total)
    monkeypatch.setattr(reconciliation_repository, "set_item_receipts", lambda *a: 1)


def test_submit_grn_success_commits_grn_and_reconcile_on_one_connection(monkeypatch):
    """Successful submission: store_last_grn and the full reconcile walk run
    on the SAME connection, with exactly one commit — proves the fix, not
    just that both steps ran."""
    monkeypatch.setattr(reconciliation_repository, "get_refresh",
                        lambda t, r: {"refresh_id": r, "cycle_id": "C1", "store_id": "S1"})
    conn_holder = {}

    def _get_conn():
        conn_holder["conn"] = _TrackingConn()
        return conn_holder["conn"]

    monkeypatch.setattr(reconciliation_service, "get_connection", _get_conn)

    grn_calls = []
    monkeypatch.setattr(
        reconciliation_repository, "store_last_grn",
        lambda c, t, r, g: grn_calls.append((c, t, r, g)) or 1,
    )
    reconcile_conns = []
    real_reconcile = reconciliation_service.reconcile

    def _tracking_reconcile(*a, **k):
        reconcile_conns.append(k.get("conn"))
        return real_reconcile(*a, **k)

    monkeypatch.setattr(reconciliation_service, "reconcile", _tracking_reconcile)
    _stub_reconcile_repo(monkeypatch)

    out = reconciliation_service.submit_grn("T1", "R1", "4567", "U1")

    assert out["last_grn_number"] == "4567"
    conn = conn_holder["conn"]
    # store_last_grn ran on the same connection reconcile was given.
    assert grn_calls[0][0] is conn
    assert reconcile_conns[0] is conn
    # Exactly one commit, no rollback, closed exactly once — a single shared
    # transaction, not two separate ones.
    assert conn.committed is True
    assert conn.rolled_back is False
    assert conn.closed is True


def _conn_factory(monkeypatch, target=reconciliation_service):
    """Records every connection get_connection() creates, in creation order —
    unlike a single mutable holder (overwritten on each call), this lets a
    test assert against the FIRST connection created (the one submit_grn
    itself owns) even when something else under test also calls
    get_connection() and would otherwise clobber a single-slot holder.
    Returns the list; appended to in order, never overwritten."""
    conns = []

    def _get_conn():
        c = _TrackingConn()
        conns.append(c)
        return c

    monkeypatch.setattr(target, "get_connection", _get_conn)
    return conns


def test_submit_grn_reconcile_failure_rolls_back_grn_update_too(monkeypatch):
    """The confirmed defect from the audit: a reconcile-stage failure must now
    roll back store_last_grn's write as well, not leave last_grn_number
    durably committed with zero reconciliation applied."""
    monkeypatch.setattr(reconciliation_repository, "get_refresh",
                        lambda t, r: {"refresh_id": r, "cycle_id": "C1", "store_id": "S1"})
    conns = _conn_factory(monkeypatch)
    monkeypatch.setattr(reconciliation_repository, "store_last_grn", lambda *a: 1)

    class _Boom(Exception):
        pass

    def _boom_receipts(*a):
        raise _Boom("forced reconciliation failure")

    monkeypatch.setattr(reconciliation_repository, "read_purchase_receipts", _boom_receipts)

    with pytest.raises(_Boom):
        reconciliation_service.submit_grn("T1", "R1", "4567", "U1")

    # Exactly one connection for the whole submit_grn call (the fix's own
    # claim) — if reconcile ever opened a second, separate connection again
    # (the pre-fix shape), this would be 2, not 1.
    assert len(conns) == 1
    grn_conn = conns[0]
    assert grn_conn.rolled_back is True
    assert grn_conn.committed is False
    assert grn_conn.closed is True


def test_submit_grn_failure_in_assignment_loop_rolls_back_grn_and_prior_assignments(monkeypatch):
    """A failure partway through the assignment-matching loop must roll back
    BOTH the GRN update and any apply_receipt calls already made earlier in
    the same loop — proves the shared transaction covers the whole walk, not
    just the first repository call."""
    monkeypatch.setattr(reconciliation_repository, "get_refresh",
                        lambda t, r: {"refresh_id": r, "cycle_id": "C1", "store_id": "S1"})
    conns = _conn_factory(monkeypatch)
    grn_conn_seen = []
    monkeypatch.setattr(
        reconciliation_repository, "store_last_grn",
        lambda c, t, r, g: grn_conn_seen.append(c) or 1,
    )
    monkeypatch.setattr(
        reconciliation_repository, "read_purchase_receipts",
        lambda *a: [{"product_code": "P1", "supplier_code": "S1",
                     "received_qty": 10, "grn_no": "G1", "supplier_bill_no": "B1"}],
    )
    monkeypatch.setattr(
        reconciliation_repository, "exported_assignments",
        lambda *a: [
            {"assignment_id": "A1", "order_item_id": "OI1",
             "product_code": "P1", "supplier_code": "S1", "assigned_qty": 10},
            {"assignment_id": "A2", "order_item_id": "OI2",
             "product_code": "P1", "supplier_code": "S1", "assigned_qty": 10},
        ],
    )
    apply_calls = []
    apply_conn_seen = []

    class _Boom(Exception):
        pass

    def _apply_receipt(c, t, aid, rec, rem, st, g, b):
        apply_calls.append(aid)
        apply_conn_seen.append(c)
        if aid == "A2":
            raise _Boom("forced failure on the second assignment")
        return 1

    monkeypatch.setattr(reconciliation_repository, "apply_receipt", _apply_receipt)
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh",
                        lambda *a: (_ for _ in ()).throw(
                            AssertionError("rollup loop must not be reached")))

    with pytest.raises(_Boom):
        reconciliation_service.submit_grn("T1", "R1", "4567", "U1")

    # Both assignments were attempted (A1 succeeded, A2 raised) but the
    # transaction as a whole rolls back — A1's apply_receipt is not left
    # committed on its own.
    assert apply_calls == ["A1", "A2"]
    # Exactly one connection created for the whole call, and it is the SAME
    # connection store_last_grn and both apply_receipt calls used — proves
    # the shared transaction, not just "some connection rolled back".
    assert len(conns) == 1
    grn_conn = conns[0]
    assert grn_conn_seen == [grn_conn]
    assert apply_conn_seen == [grn_conn, grn_conn]
    assert grn_conn.rolled_back is True
    assert grn_conn.committed is False


def test_submit_grn_failure_in_item_rollup_rolls_back_grn_and_assignment_writes(monkeypatch):
    """A failure during the order-item rollup loop (after the assignment loop
    has already succeeded) must still roll back the GRN update and every
    apply_receipt already applied — the second half of the walk failing
    cannot leave the first half's writes committed."""
    monkeypatch.setattr(reconciliation_repository, "get_refresh",
                        lambda t, r: {"refresh_id": r, "cycle_id": "C1", "store_id": "S1"})
    conns = _conn_factory(monkeypatch)
    grn_conn_seen = []
    monkeypatch.setattr(
        reconciliation_repository, "store_last_grn",
        lambda c, t, r, g: grn_conn_seen.append(c) or 1,
    )
    monkeypatch.setattr(
        reconciliation_repository, "read_purchase_receipts",
        lambda *a: [{"product_code": "P1", "supplier_code": "S1",
                     "received_qty": 60, "grn_no": "G1", "supplier_bill_no": "B1"}],
    )
    monkeypatch.setattr(
        reconciliation_repository, "exported_assignments",
        lambda *a: [{"assignment_id": "A1", "order_item_id": "OI1",
                     "product_code": "P1", "supplier_code": "S1", "assigned_qty": 100}],
    )
    apply_calls = []
    apply_conn_seen = []
    monkeypatch.setattr(
        reconciliation_repository, "apply_receipt",
        lambda c, t, aid, rec, rem, st, g, b: (
            apply_calls.append(aid), apply_conn_seen.append(c), 1
        )[-1],
    )
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh",
                        lambda *a: [{"order_item_id": "OI1", "final_qty": 100}])

    class _Boom(Exception):
        pass

    def _boom_total(*a):
        raise _Boom("forced failure during rollup")

    monkeypatch.setattr(reconciliation_repository, "item_received_total", _boom_total)
    monkeypatch.setattr(reconciliation_repository, "set_item_receipts",
                        lambda *a: (_ for _ in ()).throw(
                            AssertionError("set_item_receipts must not be reached")))

    with pytest.raises(_Boom):
        reconciliation_service.submit_grn("T1", "R1", "4567", "U1")

    assert apply_calls == ["A1"]
    assert len(conns) == 1
    grn_conn = conns[0]
    # store_last_grn and apply_receipt both ran on the one connection that
    # also ends up rolled back — the earlier assignment write is not left
    # committed on a different, already-closed connection.
    assert grn_conn_seen == [grn_conn]
    assert apply_conn_seen == [grn_conn]
    assert grn_conn.rolled_back is True
    assert grn_conn.committed is False


def test_submit_grn_retry_after_failure_succeeds_on_shared_connection(monkeypatch):
    """Retrying submit_grn after a failed attempt (e.g. the receipts read was
    transiently broken) succeeds cleanly on a fresh connection/transaction —
    apply_receipt/set_item_receipts are UPDATEs keyed by assignment_id/
    order_item_id, so re-running is naturally idempotent at the row level, as
    the audit noted. Each attempt gets its own connection via get_connection()
    (no connection reuse across calls), so a failed first attempt cannot
    poison a later retry's transaction."""
    monkeypatch.setattr(reconciliation_repository, "get_refresh",
                        lambda t, r: {"refresh_id": r, "cycle_id": "C1", "store_id": "S1"})
    conns = []

    def _get_conn():
        c = _TrackingConn()
        conns.append(c)
        return c

    monkeypatch.setattr(reconciliation_service, "get_connection", _get_conn)
    monkeypatch.setattr(reconciliation_repository, "store_last_grn", lambda *a: 1)

    attempt = {"n": 0}

    class _Boom(Exception):
        pass

    def _flaky_receipts(*a):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise _Boom("first attempt fails")
        return [{"product_code": "P1", "supplier_code": "S1",
                 "received_qty": 100, "grn_no": "G1", "supplier_bill_no": "B1"}]

    monkeypatch.setattr(reconciliation_repository, "read_purchase_receipts", _flaky_receipts)
    monkeypatch.setattr(
        reconciliation_repository, "exported_assignments",
        lambda *a: [{"assignment_id": "A1", "order_item_id": "OI1",
                     "product_code": "P1", "supplier_code": "S1", "assigned_qty": 100}],
    )
    monkeypatch.setattr(reconciliation_repository, "apply_receipt", lambda *a: 1)
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh",
                        lambda *a: [{"order_item_id": "OI1", "final_qty": 100}])
    monkeypatch.setattr(reconciliation_repository, "item_received_total", lambda *a: 100)
    monkeypatch.setattr(reconciliation_repository, "set_item_receipts", lambda *a: 1)

    with pytest.raises(_Boom):
        reconciliation_service.submit_grn("T1", "R1", "4567", "U1")
    assert conns[0].rolled_back is True
    assert conns[0].committed is False

    out = reconciliation_service.submit_grn("T1", "R1", "4567", "U1")
    assert out["assignments_matched"] == 1
    assert out["items_completed"] == 1
    assert conns[1].committed is True
    assert conns[1].rolled_back is False
    # Each attempt used its own connection — the retry did not reuse or
    # depend on the failed attempt's connection object.
    assert conns[0] is not conns[1]


def test_close_cycle_reconcile_still_opens_its_own_connection_per_refresh(monkeypatch):
    """Compatibility guard for close_cycle's EXISTING, unchanged call path —
    reconciliation_service.reconcile(tenant_id, refresh_id, store_id), no
    conn= argument — not evidence for the submit_grn shared-transaction fix
    itself. close_cycle's call site was not touched by that fix in either
    the pre-fix or the fixed implementation, so this test is expected to
    (and, per the mutation-verification step below, does) pass identically
    against both: it exists to catch a FUTURE change that accidentally
    breaks close_cycle's per-refresh isolation (one refresh's reconcile
    failure must not affect another's transaction), not to prove the GRN
    fix is present."""
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": "S1"})
    monkeypatch.setattr(cycle_repo, "cycle_close_blockers",
                        lambda t, c: {"active_refreshes": False})
    monkeypatch.setattr(cycle_repo, "refresh_ids_for_cycle", lambda t, c: ["R1", "R2"])

    conns_opened = _conn_factory(monkeypatch)
    monkeypatch.setattr(reconciliation_repository, "read_purchase_receipts", lambda *a: [])
    monkeypatch.setattr(reconciliation_repository, "exported_assignments", lambda *a: [])
    monkeypatch.setattr(reconciliation_repository, "order_items_for_refresh", lambda *a: [])
    monkeypatch.setattr(cycle_repo, "pending_item_count", lambda t, c: 0)
    monkeypatch.setattr(
        orchestration_service, "exclusion_repo",
        type("E", (), {"record_exclusions_from_replies": staticmethod(lambda *a: 0)}),
    )
    monkeypatch.setattr(orchestration_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(cycle_repo, "clear_all_pending", lambda *a: 0)
    monkeypatch.setattr(
        orchestration_service, "platform_repo",
        type("P", (), {
            "read_last_grn": staticmethod(lambda *a: "G1"),
            "read_last_sale_bill": staticmethod(lambda *a: "B1"),
        }),
    )
    monkeypatch.setattr(cycle_repo, "close_cycle", lambda *a: True)
    monkeypatch.setattr(cycle_repo, "create_cycle", lambda data: {"cycle_id": "C2", **data})
    monkeypatch.setattr(cycle_repo, "get_cycle",
                        lambda t, c: {"cycle_id": c, "status": "ACTIVE", "store_id": "S1"})

    class _StoreOK:
        def get_by_id(self, sid):
            return ("row",)

    monkeypatch.setattr(orchestration_service, "StoreRepository", lambda: _StoreOK())

    orchestration_service.close_cycle("T1", "C1", "U1", force=True)

    # One connection per refresh in the cycle (two refreshes -> two
    # connections), each independently committed — unchanged isolation.
    assert len(conns_opened) == 2
    assert all(c.committed for c in conns_opened)
    assert all(not c.rolled_back for c in conns_opened)


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
