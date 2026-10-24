"""Tests for the QTY CHECK status column (Order Workspace By Supplier +
Supplier Order Details / Assigned grids) and the OR QTY column-class fix.

Context: a prior session's grid rework left Live Stock mode's
orders_by_supplier() query, and both assigned_orders()/all_assigned_orders(),
missing om.Qtycheck from their SELECT list -- so the frontend's QTY CHECK
status column had no field to read in those two screens (it would always
render "Unknown" there, never "Checked"/"Pending"). These tests pin that the
column is present in every grid-feeding query's SQL text, so a future
refactor can't silently drop it again without a test failure.

No frontend test harness exists in this repo (no Jest/Vitest/RTL wired up
for desktop/supplier-stock-client) -- see final report. The status
CLASSIFICATION logic itself (owQtyCheckStatus in App.jsx: raw is None/
undefined -> 'unknown', Number(raw) == 1 -> 'checked', else -> 'pending') is
mirrored here in pure Python purely to pin the CONTRACT (same three cases,
same precedence) against regression, not to test the actual JS function.
"""
from __future__ import annotations

from modules.legacy_order import order_export, repository


_NMA_STORE = {"store_name": "NMA", "store_code": "1", "server_name": "SRV",
              "database": "NMA_DB", "username": "u", "password": "p"}


class _FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, *params):
        self.calls.append((sql.strip(), params))
        return self

    def fetchall(self):
        return []

    @property
    def description(self):
        return []


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_conn(monkeypatch, cur):
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _FakeConn(cur))


# ===========================================================================
# orders_by_supplier -- Qtycheck present in BOTH mode='history' and
# mode='stock' (Live Stock), not just history.
# ===========================================================================

def test_orders_by_supplier_history_mode_selects_qtycheck(monkeypatch):
    cur = _FakeCursor()
    _patch_conn(monkeypatch, cur)
    monkeypatch.setattr(repository, "backfill_is_offer", lambda sn: 0)

    repository.orders_by_supplier("NMA", "S1", "history")

    sql = cur.calls[0][0]
    assert "om.Qtycheck" in sql, "History mode must select Qtycheck for the QTY CHECK status column"


def test_orders_by_supplier_stock_mode_selects_qtycheck(monkeypatch):
    """Regression guard: this SELECT hand-writes its own column list (does
    NOT share _WORKSPACE_COLS with the history branch), which is exactly how
    Qtycheck was silently missing from Live Stock mode -- see module
    docstring."""
    cur = _FakeCursor()
    _patch_conn(monkeypatch, cur)
    monkeypatch.setattr(repository, "backfill_is_offer", lambda sn: 0)
    monkeypatch.setattr(repository, "get_store", lambda sn: _NMA_STORE)

    repository.orders_by_supplier("NMA", "S1", "stock")

    sql = cur.calls[0][0]
    assert "om.Qtycheck" in sql, "Live Stock mode must select Qtycheck for the QTY CHECK status column"


# ===========================================================================
# assigned_orders / all_assigned_orders -- Supplier Order Details grid
# ===========================================================================

def test_assigned_orders_selects_qtycheck(monkeypatch):
    cur = _FakeCursor()
    _patch_conn(monkeypatch, cur)
    monkeypatch.setattr(repository, "backfill_is_offer", lambda sn: 0)

    repository.assigned_orders("NMA", "S1")

    sql = cur.calls[0][0]
    assert "om.Qtycheck" in sql


def test_all_assigned_orders_selects_qtycheck(monkeypatch):
    cur = _FakeCursor()
    _patch_conn(monkeypatch, cur)
    monkeypatch.setattr(repository, "backfill_is_offer", lambda sn: 0)

    repository.all_assigned_orders("NMA")

    sql = cur.calls[0][0]
    assert "om.Qtycheck" in sql


# ===========================================================================
# Status classification contract (mirrors App.jsx's owQtyCheckStatus) --
# Qtycheck is a nullable BIT DEFAULT 0 (verified against the live schema:
# sys.columns/sys.default_constraints for dbo.OrderManagement.Qtycheck).
# These three cases are the full domain of values the column can hold.
# ===========================================================================

def _owQtyCheckStatus(raw):
    """Python mirror of App.jsx's owQtyCheckStatus -- pins the CONTRACT
    (precedence: None/undefined checked first, then numeric 1 vs not) so a
    future change to the real JS function has an equivalent spec to diff
    against, even without a JS test runner in this repo."""
    if raw is None:
        return "unknown"
    return "checked" if int(raw) == 1 else "pending"


def test_status_contract_checked_when_qtycheck_is_1():
    assert _owQtyCheckStatus(1) == "checked"


def test_status_contract_pending_when_qtycheck_is_0():
    assert _owQtyCheckStatus(0) == "pending"


def test_status_contract_unknown_when_qtycheck_is_null():
    """A missing/NULL status must not be reported as Checked -- the brief's
    'a failed status lookup must not display Checked' requirement."""
    assert _owQtyCheckStatus(None) == "unknown"


def test_status_contract_never_checked_for_any_non_one_value():
    for raw in (0, 2, -1, None):
        assert _owQtyCheckStatus(raw) != "checked"


# ===========================================================================
# export_order exports exactly the grid's product_codes -- no separate
# "removed" list to maintain.
# ===========================================================================

def _candidate_row(code, name="Product", qty=1):
    return {
        "ProductCode": code, "ProductName": name, "OrderQty": qty, "OrgOrderQty": qty,
        "SaleUnit": 1, "MRP": 10, "TotalStock": 5, "SLSQty": 1, "UnitDescription": "",
        "WantedType": "", "ProductTypeName": "Pharma", "Status": 0, "IsOffer": False,
    }


def test_export_order_assigns_and_exports_only_grid_products(monkeypatch):
    """Only the product_codes left in the grid are assigned and exported; a
    product the operator deleted from the grid is neither."""
    assigned = []
    monkeypatch.setattr(repository, "orders_by_supplier",
                         lambda sn, sc, m: [_candidate_row("101"), _candidate_row("102"), _candidate_row("103")])
    monkeypatch.setattr(repository, "bulk_assign_rows",
                         lambda sn, sc, sname, codes, actor: assigned.extend(codes))
    # 102 was assigned to this supplier by an earlier, unrelated action.
    monkeypatch.setattr(repository, "assigned_orders",
                         lambda sn, sc: [_candidate_row("101"), _candidate_row("102")])

    result = order_export.export_order(
        "NMA", "S1", "Supplier One", "history", 0, "actor",
        product_codes=["101"],
    )

    assert assigned == ["101"]
    assert result.count == 1
