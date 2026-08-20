"""DB-free tests for the legacy Order Management workflow state machine."""

import os
import sys
from types import SimpleNamespace

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.legacy_order import repository  # noqa: E402


class _FakeConnection:
    def __init__(self, order_id=2026082001, counts=None, state=None):
        self.order_id = order_id
        self.counts = counts or (10, 3, 2, 2, 3, 2, 8, 920.5, 2)
        self.state = state
        self.result = None
        self.writes = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self

    def execute(self, sql, *params):
        normalized = " ".join(sql.split())
        if "SELECT MAX(OrderId)" in normalized:
            self.result = (self.order_id,) if self.order_id is not None else (None,)
        elif "SELECT COUNT(*) AS TotalLines" in normalized:
            self.result = self.counts
        elif "SELECT Status, UpdatedAt" in normalized:
            self.result = self.state
        else:
            self.writes.append((normalized, params))
            self.result = None
        return self

    def fetchone(self):
        return self.result

    def nextset(self):
        return False

    def commit(self):
        self.commits += 1


def test_workflow_summary_moves_to_quantity_review(monkeypatch):
    fake = _FakeConnection()
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: fake)

    summary = repository.order_workflow_summary("NMS")

    assert summary["order_id"] == 2026082001
    assert summary["status"] == "QTY_REVIEW"
    assert summary["qty_pending"] == 3
    assert summary["assigned_value"] == 920.5
    assert summary["ready"] is False


def test_finalized_state_wins_over_derived_stage(monkeypatch):
    state = SimpleNamespace(
        Status="FINALIZED", UpdatedAt="now", UpdatedBy="admin",
        FinalizedAt="now", Note="approved",
    )
    fake = _FakeConnection(counts=(10, 0, 5, 5, 0, 0, 20, 1500, 3), state=state)
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: fake)

    summary = repository.order_workflow_summary("NMS")

    assert summary["status"] == "FINALIZED"
    assert summary["ready"] is True
    assert summary["updated_by"] == "admin"


def test_finalize_rejects_incomplete_order(monkeypatch):
    fake = _FakeConnection(counts=(10, 1, 4, 4, 1, 0, 20, 1500, 3))
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: fake)

    with pytest.raises(ValueError, match="1 quantity checks and 1 supplier assignments"):
        repository.set_order_workflow_finalized("NMS", "admin")


def test_finalize_persists_state_and_audit(monkeypatch):
    fake = _FakeConnection(counts=(10, 0, 5, 5, 0, 0, 20, 1500, 3))
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: fake)
    monkeypatch.setattr(
        repository, "order_workflow_summary",
        lambda store: {"store_name": store, "status": "FINALIZED"},
    )

    result = repository.set_order_workflow_finalized("NMS", "admin", "checked")

    assert result["status"] == "FINALIZED"
    assert any("MERGE dbo.LegacyOrderWorkflow" in sql for sql, _ in fake.writes)
    assert any("INSERT dbo.LegacyOrderWorkflowAudit" in sql for sql, _ in fake.writes)
    assert fake.commits == 1
