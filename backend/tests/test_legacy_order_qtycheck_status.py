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
# export_order's removed_product_codes hard exclusion -- a second,
# independent guard against a deleted row still appearing in an export, even
# if product_codes is ever stale (see schemas.ExportOrderRequest docstring
# and order_export.export_order docstring for the full rationale).
# ===========================================================================

def _candidate_row(code, name="Product", qty=1):
    return {
        "ProductCode": code, "ProductName": name, "OrderQty": qty, "OrgOrderQty": qty,
        "SaleUnit": 1, "MRP": 10, "TotalStock": 5, "SLSQty": 1, "UnitDescription": "",
        "WantedType": "", "ProductTypeName": "Pharma", "Status": 0, "IsOffer": False,
    }


def test_export_order_excludes_removed_product_from_assignment(monkeypatch):
    """A product in removed_product_codes must never be assigned, even if it
    is still present in the server-side re-resolved candidate set."""
    assigned = []
    monkeypatch.setattr(repository, "orders_by_supplier",
                         lambda sn, sc, m: [_candidate_row("101"), _candidate_row("102")])
    monkeypatch.setattr(repository, "bulk_assign_rows",
                         lambda sn, sc, sname, codes, actor: assigned.extend(codes))
    monkeypatch.setattr(repository, "assigned_orders",
                         lambda sn, sc: [_candidate_row("101")])  # 102 was excluded, never assigned

    order_export.export_order(
        "NMA", "S1", "Supplier One", "history", 0, "actor",
        product_codes=["101", "102"], removed_product_codes=["102"],
    )

    assert "102" not in assigned
    assert "101" in assigned


def test_export_order_excludes_removed_product_from_final_rows(monkeypatch):
    """Even if assigned_orders() (sourced from the live DB, not today's
    session) still returns a removed product -- e.g. because it was assigned
    by a SEPARATE, earlier action -- it must be excluded from the exported
    workbook rows, not just skipped for assignment."""
    monkeypatch.setattr(repository, "orders_by_supplier", lambda sn, sc, m: [_candidate_row("101")])
    monkeypatch.setattr(repository, "bulk_assign_rows", lambda sn, sc, sname, codes, actor: None)
    # Simulate the exact reported bug: assigned_orders() returns a row the
    # operator deleted this session (assigned via some earlier, unrelated action).
    monkeypatch.setattr(repository, "assigned_orders",
                         lambda sn, sc: [_candidate_row("101"), _candidate_row("999", name="NIFUTIN TAB")])

    result = order_export.export_order(
        "NMA", "S1", "Supplier One", "history", 0, "actor",
        product_codes=["101", "999"], removed_product_codes=["999"],
    )

    assert result.count == 1  # only 101 -- 999 (NIFUTIN TAB) excluded despite assigned_orders() returning it


def test_export_order_assigned_view_also_honors_removed_product_codes(monkeypatch):
    """The Assigned-view export path (product_codes=None) must also respect
    removed_product_codes, not just the By-Supplier curated-list path."""
    monkeypatch.setattr(repository, "assigned_orders",
                         lambda sn, sc: [_candidate_row("101"), _candidate_row("999")])

    result = order_export.export_order(
        "NMA", "S1", "Supplier One", "history", 0, "actor",
        removed_product_codes=["999"],
    )

    assert result.count == 1
