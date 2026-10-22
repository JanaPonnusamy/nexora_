"""Step 4 — durable VPL History persistence repository (DB-free).

Tests vpl_history_repository.py's SQL call shape and transaction behavior
against migration 0030_vpl_history_persistence.sql's schema (NOT APPLIED).
This is a new module, separate from vpl_history.py's in-memory prototype —
not called by any live route yet.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement import vpl_history_repository as repo  # noqa: E402


class _FakeCursor:
    def __init__(self, fetchone_sequence=None):
        self.executed = []
        self._fetchone_sequence = list(fetchone_sequence or [])
        self.rowcount = 1

    def execute(self, sql, params):
        self.executed.append((sql, tuple(params)))

    def fetchone(self):
        if self._fetchone_sequence:
            return self._fetchone_sequence.pop(0)
        return None


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _line(**over):
    base = {
        "order_item_id": "OI1", "product_id": "P1", "product_code": "PARA-500",
        "suggested_qty": 100, "final_qty": 100, "manual_override": False,
        "item_status": "review", "skip_reason": None, "reviewed_by": None,
        "reviewed_at": None, "reason_code": "SOME_REASON", "row_version": 2,
        "carried_forward": False,
    }
    base.update(over)
    return base


# ==========================================================================
# write_history_batch
# ==========================================================================

def test_write_history_batch_inserts_batch_then_line_then_assignments():
    cursor = _FakeCursor(fetchone_sequence=[("HIST1",), ("ASG-ROW",)])
    conn = _FakeConn(cursor)

    history_id = repo.write_history_batch(
        conn, "T1", "S1", "C1", "R_OLD", "R_NEW",
        lines=[_line()],
        assignments_by_order_item_id={
            "OI1": [{"assignment_id": "A1", "supplier_code": "SUP1",
                     "assigned_qty": 50, "assignment_status": "draft"}]
        },
        created_by="U1",
    )
    assert history_id == "HIST1"
    # batch insert, then one line insert, then one assignment insert — in order
    assert "INSERT INTO procurement.vpl_history_batch" in cursor.executed[0][0]
    assert "INSERT INTO procurement.vpl_history_line" in cursor.executed[1][0]
    assert "INSERT INTO procurement.vpl_history_assignment" in cursor.executed[2][0]
    # line insert carries the history_id returned by the batch insert
    assert cursor.executed[1][1][0] == "HIST1"
    assert cursor.executed[1][1][1] == "OI1"
    # assignment insert carries the same history_id + order_item_id link
    assert cursor.executed[2][1][0] == "HIST1"
    assert cursor.executed[2][1][1] == "A1"
    assert cursor.executed[2][1][2] == "OI1"


def test_write_history_batch_with_no_assignments_skips_the_assignment_insert():
    cursor = _FakeCursor(fetchone_sequence=[("HIST1",)])
    conn = _FakeConn(cursor)

    repo.write_history_batch(
        conn, "T1", "S1", "C1", "R_OLD", "R_NEW",
        lines=[_line()], assignments_by_order_item_id={}, created_by="U1",
    )
    kinds = [sql for sql, _ in cursor.executed]
    assert sum("vpl_history_assignment" in k for k in kinds) == 0
    assert sum("vpl_history_line" in k for k in kinds) == 1


def test_write_history_batch_multiple_lines_each_get_their_own_row():
    cursor = _FakeCursor(fetchone_sequence=[("HIST1",)])
    conn = _FakeConn(cursor)

    repo.write_history_batch(
        conn, "T1", "S1", "C1", "R_OLD", "R_NEW",
        lines=[_line(order_item_id="OI1"), _line(order_item_id="OI2", product_code="AMOX-250")],
        assignments_by_order_item_id={}, created_by="U1",
    )
    line_inserts = [p for sql, p in cursor.executed if "vpl_history_line" in sql]
    assert len(line_inserts) == 2
    assert {p[1] for p in line_inserts} == {"OI1", "OI2"}


def test_write_history_batch_line_count_matches_lines_supplied():
    cursor = _FakeCursor(fetchone_sequence=[("HIST1",)])
    conn = _FakeConn(cursor)

    repo.write_history_batch(
        conn, "T1", "S1", "C1", "R_OLD", "R_NEW",
        lines=[_line(order_item_id="OI1"), _line(order_item_id="OI2")],
        assignments_by_order_item_id={}, created_by="U1",
    )
    batch_sql, batch_params = cursor.executed[0]
    assert "line_count" in batch_sql
    # line_count is the 7th bound param (tenant, store, cycle, source,
    # successor, rule_snapshot_id, line_count, created_by)
    assert batch_params[6] == 2


def test_write_history_batch_null_product_code_is_accepted():
    cursor = _FakeCursor(fetchone_sequence=[("HIST1",)])
    conn = _FakeConn(cursor)

    repo.write_history_batch(
        conn, "T1", "S1", "C1", "R_OLD", "R_NEW",
        lines=[_line(product_code=None, product_id="P1")],
        assignments_by_order_item_id={}, created_by="U1",
    )
    line_sql, line_params = cursor.executed[1]
    assert line_params[7] is None  # product_code
    assert line_params[6] == "P1"  # product_id still present


# ==========================================================================
# Removed-line upsert / restore
# ==========================================================================

def test_upsert_removed_line_returns_new_id():
    cursor = _FakeCursor(fetchone_sequence=[("REM1",)])
    conn = _FakeConn(cursor)

    removed_id = repo.upsert_removed_line(
        conn, "T1", "S1", "C1", "P1", "PARA-500",
        originating_refresh_id="R_OLD", originating_cycle_id="C1",
        removed_during_refresh_id="R_NEW", final_qty=40, manual_override=True,
        override_reason="demand spike", supplier_code="SUP1", assigned_qty=10,
        removed_by="U1",
    )
    assert removed_id == "REM1"
    assert "INSERT INTO procurement.vpl_removed_line" in cursor.executed[0][0]


def test_restore_removed_line_returns_none_when_no_active_row():
    cursor = _FakeCursor(fetchone_sequence=[None])
    conn = _FakeConn(cursor)
    out = repo.restore_removed_line(conn, "T1", "S1", "C1", "P1", "U1")
    assert out is None
    # No UPDATE attempted when there's nothing to restore.
    assert not any("UPDATE" in sql for sql, _ in cursor.executed)


def test_restore_removed_line_restores_and_returns_preserved_fields():
    cursor = _FakeCursor(fetchone_sequence=[
        ("REM1", 40, 1, "demand spike", "SUP1", 10),
    ])
    conn = _FakeConn(cursor)
    out = repo.restore_removed_line(conn, "T1", "S1", "C1", "P1", "U1")
    assert out["removed_id"] == "REM1"
    assert out["final_qty"] == 40
    assert out["manual_override"] is True
    assert out["supplier_code"] == "SUP1"
    assert out["assigned_qty"] == 10
    update_calls = [sql for sql, _ in cursor.executed if "UPDATE" in sql]
    assert len(update_calls) == 1
    assert "restored_at = GETDATE()" in update_calls[0]


def test_restore_removed_line_fails_closed_on_concurrent_double_restore():
    """SELECT finds an active row, but the UPDATE's rowcount is 0 (someone
    else's UPDATE won the race first) — must return None, not the stale
    pre-race row, since a caller using it would double-apply the restore."""
    cursor = _FakeCursor(fetchone_sequence=[
        ("REM1", 40, 0, None, None, None),
    ])
    cursor.rowcount = 0
    conn = _FakeConn(cursor)
    out = repo.restore_removed_line(conn, "T1", "S1", "C1", "P1", "U1")
    assert out is None
