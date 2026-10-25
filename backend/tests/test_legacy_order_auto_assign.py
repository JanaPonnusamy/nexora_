"""Bulk Assign · Best Margin -- the supplier-selection rule behind the Order
Workspace process after Qty Check (repository.pick_auto_assign_supplier /
receipt_margin): best margin over the last 5 supplies, else the most
frequent supplier."""
from __future__ import annotations

import datetime

import pytest

from modules.legacy_order import repository

ACTIVE = {"A": "Alpha", "B": "Beta", "C": "Gamma"}


def _r(code, margin, day):
    return {"supplier_code": code, "margin": margin, "grn_date": datetime.date(2026, 10, day)}


def test_receipt_margin_spreads_cost_over_free_qty():
    assert repository.receipt_margin(100, 80, 10, 0) == pytest.approx(20.0)
    # 10 + 2 free: net unit cost 80 * 10 / 12 = 66.67 -> 33.33 %
    assert repository.receipt_margin(100, 80, 10, 2) == pytest.approx(33.333, abs=0.01)


@pytest.mark.parametrize("args", [(0, 80, 10, 0), (100, 0, 10, 0), (100, 80, 0, 0), (None, None, None, None)])
def test_receipt_margin_none_without_price_or_qty(args):
    assert repository.receipt_margin(*args) is None


def test_best_margin_wins_on_each_suppliers_latest_supply():
    receipts = [_r("A", 18.0, 20), _r("B", 22.0, 15), _r("A", 30.0, 10)]
    # A's latest supply is 18 %, so B (22 %) wins despite A's old 30 %.
    assert repository.pick_auto_assign_supplier(receipts, [], ACTIVE) == ("B", "best_margin", 22.0, 1)


def test_margin_tie_goes_to_more_supplies_then_most_recent():
    receipts = [_r("A", 20.0, 20), _r("B", 20.0, 15), _r("B", 20.0, 10)]
    assert repository.pick_auto_assign_supplier(receipts, [], ACTIVE)[0] == "B"
    receipts = [_r("A", 20.0, 20), _r("B", 20.0, 15)]
    assert repository.pick_auto_assign_supplier(receipts, [], ACTIVE)[0] == "A"


def test_inactive_or_unpriced_supplies_are_ignored():
    receipts = [_r("X", 50.0, 20), _r("B", None, 18), _r("C", 12.0, 10)]
    assert repository.pick_auto_assign_supplier(receipts, [], ACTIVE)[0] == "C"


def test_no_usable_supply_falls_back_to_most_frequent_active_supplier():
    assert repository.pick_auto_assign_supplier([], ["X", "B", "A"], ACTIVE) == ("B", "most_frequent", None, 0)
    assert repository.pick_auto_assign_supplier([_r("X", 40.0, 1)], ["A"], ACTIVE)[:2] == ("A", "most_frequent")


def test_nothing_known_leaves_the_line_unassigned():
    assert repository.pick_auto_assign_supplier([], ["X"], ACTIVE) == (None, None, None, 0)
