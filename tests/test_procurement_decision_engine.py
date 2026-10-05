"""Procurement Phase 3 — Decision Engine tests (DB-free).

Unit-tests the business rules against the catalogue worked example (PARA-500)
and its edge cases, and verifies the engine orchestration bulk-writes without
N+1 queries. No database connection is opened.
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement import decision_rules as rules  # noqa: E402


def _params(rolling=90, min_days=10, max_days=20):
    return rules.DecisionParameters(
        rolling_days=rolling, min_days=min_days, max_days=max_days
    )


def _para500(**overrides):
    """The catalogue running example: window 900, peak day 40, peak bill 60,
    120 bills; stock 30, pending receivable 50, in transit 0, reserved 10."""
    src = {
        "product_id": "PARA-500",
        "is_active": True,
        "dont_consider": False,
        "window_sales_qty": 900.0,
        "max_day_sale_qty": 40.0,
        "max_bill_qty": 60.0,
        "billing_frequency": 120,
        "current_stock": 30.0,
        "pending_receivable": 50.0,
        "in_transit": 0.0,
        "reserved": 10.0,
        # Eligible by the legacy date gates: sold today, last GRN a month ago.
        "last_sale_date": datetime.now(),
        "last_received_date": datetime.now() - timedelta(days=30),
    }
    src.update(overrides)
    return src


# --------------------------------------------------------------------------
# Worked example (PR-BR-002..015)
# --------------------------------------------------------------------------

def test_para500_full_trace():
    out = rules.evaluate(_para500(), _params())
    assert out["avg_daily_sales"] == 10.0            # 900/90
    assert out["effective_available_qty"] == 70.0    # 30+50+0-10
    assert out["days_cover"] == 7.0                  # 70/10
    assert out["movement_class"] == "MEDIUM"         # 10 >= 10
    assert out["stock_status"] == "SAFE"             # 3 <= 7 <= 15
    assert out["target_stock_qty"] == 200.0          # 10*20
    assert out["raw_required_qty"] == 130.0          # 200-70
    assert out["final_required_qty"] == 130          # ceil(max(130,40,60))
    assert out["suggested_qty"] == 130
    assert out["procurement_action"] == rules.ACTION_INCLUDE
    assert out["reason_code"] == rules.INCLUDED_BELOW_MIN_DAYS
    assert out["trigger_reason"] == rules.COVERAGE


def test_para500_strip_conversion():
    # Same worked example, but the product sells in strips of 10 (SaleUnit=10):
    # suggested_qty must come out in strips, not loose units.
    out = rules.evaluate(_para500(sale_unit=10.0), _params())
    assert out["final_required_qty"] == 13           # ceil(130/10)
    assert out["suggested_qty"] == 13
    assert out["procurement_action"] == rules.ACTION_INCLUDE


# --------------------------------------------------------------------------
# Atomic rules
# --------------------------------------------------------------------------

def test_average_daily_sales_uses_full_window():
    assert rules.average_daily_sales(900, 90) == 10.0
    assert rules.average_daily_sales(0, 90) == 0.0
    assert rules.average_daily_sales(900, 0) == 0.0   # guarded


def test_effective_available_components():
    assert rules.effective_available(30, 50, 0, 10) == 70


def test_days_cover_zero_when_not_selling():
    assert rules.days_cover(70, 0) == 0.0


def test_movement_class_buckets():
    p = _params()
    assert rules.movement_class(50, p) == "FAST"
    assert rules.movement_class(10, p) == "MEDIUM"
    assert rules.movement_class(1, p) == "SLOW"
    assert rules.movement_class(0, p) == "NONMOVING"


def test_stock_status_buckets():
    p = _params()
    assert rules.stock_status(0, 0, p) == "OUT"
    assert rules.stock_status(5, 2, p) == "LOW"
    assert rules.stock_status(70, 7, p) == "SAFE"
    assert rules.stock_status(500, 40, p) == "OVERSTOCK"


def test_final_required_determinants():
    # coverage binding (no sale_unit -> strip qty falls back to loose qty)
    # target=130 dominates max_day=60/max_bill=20; required = 130-40 = 90
    assert rules.final_required(130, 40, 60, 20) == (90, 90, 90, rules.COVERAGE)
    # spike floor binding (day)
    assert rules.final_required(10, 5, 40, 20) == (35, 35, 35, rules.SPIKE_PROTECTION)
    # max-bill floor binding
    assert rules.final_required(10, 5, 20, 55) == (50, 50, 50, rules.MAX_BILL_TRIGGER)
    # legacy single-line spike floor binding (max_line_sale_qty) -- parity add
    assert rules.final_required(10, 5, 20, 25, max_line_sale_qty=70) == (65, 65, 65, rules.SPIKE_PROTECTION)


def test_final_required_strip_conversion():
    # PR-BR-007/008/009 legacy parity: divide the loose shortfall by SaleUnit
    # and ceiling it, mirroring order_local/remote.sql's Orderqty.
    # target=130 dominates; required = 130-40 = 90; strips = ceil(90/10) = 9
    assert rules.final_required(130, 40, 60, 20, sale_unit=10) == (90, 90, 9, rules.COVERAGE)
    assert rules.final_required(121, 40, 60, 20, sale_unit=10) == (81, 81, 9, rules.COVERAGE)
    # SaleUnit <= 0 falls back to loose quantity instead of zeroing the order.
    assert rules.final_required(130, 40, 60, 20, sale_unit=0) == (90, 90, 90, rules.COVERAGE)


# --------------------------------------------------------------------------
# Inclusion / exclusion (PR-BR-004/013/009 + PR-BR-015 reason codes)
# --------------------------------------------------------------------------

def test_excluded_not_selling():
    out = rules.evaluate(_para500(window_sales_qty=0), _params())
    assert out["procurement_action"] == rules.ACTION_EXCLUDE
    assert out["reason_code"] == rules.EXCLUDED_NOT_SELLING
    assert out["suggested_qty"] == 0


def test_excluded_adequate_cover():
    # plenty of stock -> cover >= min_days
    out = rules.evaluate(_para500(current_stock=2000), _params())
    assert out["reason_code"] == rules.EXCLUDED_ADEQUATE_COVER
    assert out["suggested_qty"] == 0


def test_excluded_zero_required():
    # sells, cover below min, but effective available already meets target:
    # avg=1, eff=100, cover=100<200 -> candidate; target=1*50=50; coverage=-50 -> final 0
    out = rules.evaluate(
        _para500(window_sales_qty=90, current_stock=100, pending_receivable=0,
                 reserved=0, max_day_sale_qty=0, max_bill_qty=0),
        _params(min_days=200, max_days=50),
    )
    assert out["reason_code"] == rules.EXCLUDED_ZERO_REQUIRED
    assert out["suggested_qty"] == 0


def test_excluded_stale_sale():
    # sells in the window but last bill is older than the 10-day recency floor
    out = rules.evaluate(
        _para500(last_sale_date=datetime.now() - timedelta(days=15)), _params()
    )
    assert out["procurement_action"] == rules.ACTION_EXCLUDE
    assert out["reason_code"] == rules.EXCLUDED_STALE_SALE
    assert out["suggested_qty"] == 0


def test_excluded_recently_received():
    # recently sold, but the last GRN is AFTER the last sale: purchased, not yet
    # moved — the legacy `ps.lastsaledate >= ps.LastReceivedDate` gate.
    out = rules.evaluate(
        _para500(
            last_sale_date=datetime.now() - timedelta(days=3),
            last_received_date=datetime.now() - timedelta(days=1),
        ),
        _params(),
    )
    assert out["procurement_action"] == rules.ACTION_EXCLUDE
    assert out["reason_code"] == rules.EXCLUDED_RECENTLY_RECEIVED
    assert out["suggested_qty"] == 0


def test_excluded_missing_grn_watermark():
    # sold recently but no GRN watermark at all -> NULL comparison excludes,
    # exactly as the legacy LEFT JOIN does.
    out = rules.evaluate(_para500(last_received_date=None), _params())
    assert out["reason_code"] == rules.EXCLUDED_RECENTLY_RECEIVED


def test_excluded_inactive_and_flagged():
    assert rules.evaluate(_para500(is_active=False), _params())["reason_code"] \
        == rules.EXCLUDED_INACTIVE
    assert rules.evaluate(_para500(dont_consider=True), _params())["reason_code"] \
        == rules.EXCLUDED_FLAGGED


def test_spike_floor_included_binding():
    # low coverage but a big single-day sale forces a floor
    out = rules.evaluate(
        _para500(window_sales_qty=90, current_stock=8, pending_receivable=0,
                 reserved=0, max_day_sale_qty=40, max_bill_qty=5),
        _params(min_days=20, max_days=10),
    )
    # avg=1, eff=8, cover=8<20 include; target=10; coverage=2; max(2,40,5)=40
    assert out["procurement_action"] == rules.ACTION_INCLUDE
    assert out["final_required_qty"] == 40
    assert out["trigger_reason"] == rules.SPIKE_PROTECTION


# --------------------------------------------------------------------------
# Legacy parity additions: average-per-bill MinQty floor, single-line spike
# metric, and the "Additional Row" rare-mover top-up.
# --------------------------------------------------------------------------

def test_min_qty_floor_matches_legacy_formula():
    # legacy: minqty = MAX(CEIL(avg*MinDays), CEIL(slsqty/Frequency))
    assert rules.min_qty_floor(avg_daily_sales=2, min_days=10, window_sales_qty=90,
                                billing_frequency=12) == 20   # by_days=20, by_bill=ceil(7.5)=8
    assert rules.min_qty_floor(avg_daily_sales=1, min_days=5, window_sales_qty=900,
                                billing_frequency=12) == 75   # by_days=5, by_bill=ceil(75)=75
    assert rules.min_qty_floor(0, 10, 0, 0) == 0


def test_qualifies_via_per_bill_floor_despite_adequate_days_cover():
    # A lumpy/slow mover: low day-average (cover looks "adequate" by ratio)
    # but a large per-bill floor from rare, big-quantity bills -- legacy's
    # minqty>TotalStock gate would still order this; the pure days-cover gate
    # would not. window=200 over 90d -> avg~2.22, but only 4 bills so
    # avg-per-bill floor = ceil(200/4) = 50, well above the small stock held.
    out = rules.evaluate(
        _para500(window_sales_qty=200, billing_frequency=4, current_stock=12,
                  pending_receivable=0, in_transit=0, reserved=0,
                  max_day_sale_qty=0, max_bill_qty=0),
        _params(min_days=5, max_days=10),
    )
    # avg=200/90=2.22, eff=12, cover=12/2.22=5.4 >= min_days(5) -> NOT qualified
    # by cover alone, but min_qty_floor=max(ceil(2.22*5)=12, ceil(200/4)=50)=50 > eff(12)
    assert out["days_cover"] >= 5
    assert out["procurement_action"] == rules.ACTION_INCLUDE
    assert "per-bill MinQty floor" in out["reason_text"]


def test_excluded_adequate_cover_still_excludes_when_no_lumpy_pattern():
    # Regression guard: the new OR gate must not re-qualify products that
    # legitimately have adequate cover AND no meaningful per-bill floor.
    out = rules.evaluate(_para500(current_stock=2000), _params())
    assert out["reason_code"] == rules.EXCLUDED_ADEQUATE_COVER
    assert out["suggested_qty"] == 0


def test_max_line_sale_qty_spike_parity():
    # Legacy's exact spike metric (MaxSalesQtyInBill = MAX single sale-line
    # qty) must floor the gross target even when NEXORA's own day/bill sums
    # are smaller -- restores legacy's own floor as a superset term.
    out = rules.evaluate(
        _para500(window_sales_qty=90, current_stock=5, pending_receivable=0,
                  reserved=0, max_day_sale_qty=10, max_bill_qty=10,
                  max_line_sale_qty=90),
        _params(min_days=20, max_days=10),
    )
    assert out["procurement_action"] == rules.ACTION_INCLUDE
    assert out["final_required_qty"] == 85       # ceil(max(10,10,10,90) - 5)
    assert out["trigger_reason"] == rules.SPIKE_PROTECTION


def test_rare_mover_topup_matches_legacy_additional_row():
    # legacy "Additional Row": TotalStock<=1, minqty<=1, Frequency>1, slsqty>1,
    # sold recently, sold after last GRN, not already a normal candidate ->
    # forced OrderQty=1. Low, infrequent sales keep both cover and the
    # per-bill floor from qualifying it any other way.
    out = rules.evaluate(
        _para500(window_sales_qty=3, billing_frequency=3, current_stock=1,
                  pending_receivable=0, in_transit=0, reserved=0,
                  max_day_sale_qty=0, max_bill_qty=0),
        _params(min_days=1, max_days=5),
    )
    assert out["procurement_action"] == rules.ACTION_INCLUDE
    assert out["reason_code"] == rules.INCLUDED_RARE_MOVER_TOPUP
    assert out["trigger_reason"] == rules.RARE_MOVER_TOPUP
    assert out["suggested_qty"] == 1
    assert out["final_required_qty"] == 1


def test_rare_mover_topup_not_triggered_for_single_bill():
    # Frequency<=1 must NOT take the "Additional Row" top-up path (legacy
    # requires Frequency>1) -- it still qualifies via the per-bill floor, but
    # sizes to zero required units and is excluded on that basis instead.
    out = rules.evaluate(
        _para500(window_sales_qty=3, billing_frequency=1, current_stock=1,
                  pending_receivable=0, in_transit=0, reserved=0,
                  max_day_sale_qty=0, max_bill_qty=0),
        _params(min_days=1, max_days=5),
    )
    assert out["reason_code"] != rules.INCLUDED_RARE_MOVER_TOPUP
    assert out["procurement_action"] == rules.ACTION_EXCLUDE


# --------------------------------------------------------------------------
# Parameter validation (PR-BR-005/016)
# --------------------------------------------------------------------------

def test_parameter_validation():
    _params().validate()  # ok
    with pytest.raises(ValueError):
        rules.DecisionParameters(rolling_days=0, min_days=10, max_days=20).validate()
    with pytest.raises(ValueError):
        rules.DecisionParameters(rolling_days=90, min_days=0, max_days=20).validate()
    with pytest.raises(ValueError):
        rules.DecisionParameters(rolling_days=90, min_days=20, max_days=10).validate()


# --------------------------------------------------------------------------
# Orchestration: bulk write, no N+1  (uses stubs, no DB)
# --------------------------------------------------------------------------

class _FakeConn:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_engine_is_bulk_and_no_n_plus_1(monkeypatch):
    from modules.procurement import decision_service, decision_repository

    calls = {"load_source": 0, "bulk_insert": 0, "insert_rows": 0}

    refresh = {
        "refresh_id": "R1", "cycle_id": "C1", "store_id": None,
        "rolling_days": 90, "min_days": 10, "max_days": 20,
        "snapshot_status": "Draft",
    }
    source = [_para500(product_id=f"P{i}") for i in range(500)]

    monkeypatch.setattr(decision_service, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        decision_repository, "get_refresh_for_generation",
        lambda t, r: refresh,
    )

    def _load_source(conn, tenant_id, store_id, params):
        calls["load_source"] += 1
        return source

    def _bulk_insert(conn, rows):
        calls["bulk_insert"] += 1
        calls["insert_rows"] = len(rows)
        return len(rows)

    monkeypatch.setattr(decision_repository, "load_source", _load_source)
    monkeypatch.setattr(decision_repository, "mark_generating", lambda *a: 1)
    monkeypatch.setattr(decision_repository, "clear_products", lambda *a: 0)
    monkeypatch.setattr(decision_repository, "bulk_insert_products", _bulk_insert)
    monkeypatch.setattr(decision_repository, "finalize", lambda *a: None)

    result = decision_service.generate_vpl("T1", "R1")

    assert result["generated_product_count"] == 500
    assert result["included_count"] == 500          # all PARA-500 -> included
    # exactly one source read and one bulk insert regardless of row count
    assert calls["load_source"] == 1
    assert calls["bulk_insert"] == 1
    assert calls["insert_rows"] == 500
