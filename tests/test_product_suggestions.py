"""Suggestion panel supplier ranking (pure). No DB."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement.suggestion_service import _merge_suppliers, rank_suppliers  # noqa: E402


def _s(code, freq, last, ptr, live=None):
    return {"supplier_code": code, "purchase_frequency": freq, "last_grn_date": last, "ptr": ptr, "live_stock": live}


def test_best_frequent_latest_tags():
    ranked = rank_suppliers([
        _s("A", 17, "2026-09-08", 330.6),
        _s("B", 9, "2026-06-18", 330.6),
        _s("C", 2, "2025-07-26", 296.5),
    ])
    assert ranked[0]["supplier_code"] == "A"
    assert set(ranked[0]["tags"]) >= {"best", "frequent", "latest"}
    assert "best" not in ranked[1]["tags"]


def test_frequent_and_latest_can_differ_from_best():
    ranked = rank_suppliers([
        _s("RECENT", 5, "2026-08-26", 99.0),
        _s("OFTEN", 15, "2025-12-12", 92.0),
    ])
    by = {r["supplier_code"]: r["tags"] for r in ranked}
    assert "frequent" in by["OFTEN"]
    assert "latest" in by["RECENT"]


def test_live_stock_adds_weight_and_tag():
    ranked = rank_suppliers([_s("X", 3, "2026-01-01", 10.0), _s("Y", 3, "2026-01-01", 10.0, live=40)])
    assert ranked[0]["supplier_code"] == "Y"
    assert "live" in ranked[0]["tags"]


def test_no_history_supplier_is_not_frequent():
    ranked = rank_suppliers([_s("L", 0, None, None, live=5)])
    assert ranked[0]["tags"] == ["best", "live"]


def test_empty():
    assert rank_suppliers([]) == []


def test_merge_live_only_supplier_and_warehouse_label():
    merged = _merge_suppliers(
        [{"supplier_code": "1", "supplier_name": "S1", "purchase_frequency": 4, "last_grn_date": "2026-01-01", "last_purchase_rate": 10}],
        [{"supplier_code": "1", "available_stock": 7, "ptr": 9},
         {"supplier_code": "ST_2", "available_stock": 19, "ptr": None}],
    )
    by = {m["supplier_code"]: m for m in merged}
    assert by["1"]["live_stock"] == 7 and by["1"]["ptr"] == 10
    assert by["ST_2"]["is_warehouse"] is True
    assert "Warehouse" in by["ST_2"]["supplier_name"]
    assert "warehouse" in rank_suppliers(merged)[[r["supplier_code"] for r in rank_suppliers(merged)].index("ST_2")]["tags"]
