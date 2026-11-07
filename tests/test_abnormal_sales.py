"""Abnormal bill-sale rule (PRR-SALE-ABNORMAL / PRR-SALE-WARNING). Pure, no DB."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement.abnormal_sales import classify_bills, classify_product  # noqa: E402
from modules.procurement.rules_catalog import BY_ID  # noqa: E402


def _bills(*qtys, flagged=()):
    return [{"bill_no": f"B{i}", "qty": q, "dont_consider": i in flagged} for i, q in enumerate(qtys)]


def test_bulk_bill_is_abnormal_against_the_other_bills():
    # usual bill 2 (avg of the other four), bulk bill 20 -> 10x
    out = classify_product(_bills(2, 2, 2, 2, 20))
    assert out["level"] == "abnormal"
    assert out["bills"][0]["bill_no"] == "B4"
    assert out["bills"][0]["avg_other"] == 2
    assert out["bills"][0]["ratio"] == 10


def test_three_times_is_a_warning_and_below_is_nothing():
    assert classify_product(_bills(2, 2, 2, 6))["level"] == "warning"
    assert classify_product(_bills(2, 2, 2, 5)) is None


def test_exactly_five_times_is_abnormal():
    assert classify_product(_bills(2, 2, 10))["level"] == "abnormal"


def test_needs_two_other_bills():
    # one other bill is not an average to compare against
    assert classify_product(_bills(1, 50)) is None


def test_marked_bill_is_left_out_of_the_average_and_shown_as_reviewed():
    out = classify_product(_bills(2, 2, 2, 40, flagged={3}))
    assert out["level"] == "reviewed"
    assert out["bills"][0]["dont_consider"] is True
    # the average the PM sees is the counted bills only
    assert out["avg_bill_qty"] == 2
    assert out["bill_count"] == 3


def test_zero_and_negative_quantities_are_ignored():
    assert classify_product(_bills(0, -5, 2, 2, 2)) is None


def test_custom_thresholds():
    assert classify_product(_bills(2, 2, 2, 6), abnormal=3, warning=2)["level"] == "abnormal"


def test_classify_bills_groups_by_product():
    rows = [
        {"product_code": "A", "qty": q, "dont_consider": False} for q in (1, 1, 1, 9)
    ] + [
        {"product_code": "B", "qty": q, "dont_consider": False} for q in (5, 5, 5, 6)
    ]
    out = classify_bills(rows)
    assert set(out) == {"A"}
    assert out["A"]["product_code"] == "A"


def test_rulebook_defaults():
    assert BY_ID["PRR-SALE-ABNORMAL"].default_value == 5
    assert BY_ID["PRR-SALE-WARNING"].default_value == 3
    assert BY_ID["PRR-SALE-WARNING"].default_value < BY_ID["PRR-SALE-ABNORMAL"].default_value


def test_legacy_list_is_computed_once_per_store_and_cleared_by_a_mark(monkeypatch):
    # Overlapping legacy reads starved the export (2026-11-02): concurrent and
    # repeated calls share one computation until a dont-consider mark.
    import threading
    import time
    from modules.procurement import abnormal_sales_service as svc

    calls = []

    def slow_compute(store_name):
        calls.append(store_name)
        time.sleep(0.2)
        return {"items": [], "n": len(calls)}

    monkeypatch.setattr(svc, "_compute_legacy_abnormal_sales", slow_compute)
    monkeypatch.setattr(svc, "_legacy_cache", {})
    results = []
    threads = [threading.Thread(target=lambda: results.append(svc.legacy_abnormal_sales("NMS"))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == ["NMS"]
    assert all(r["n"] == 1 for r in results)
    assert svc.legacy_abnormal_sales("nms ")["n"] == 1

    svc.invalidate_legacy_cache("NMS")
    assert svc.legacy_abnormal_sales("NMS")["n"] == 2
