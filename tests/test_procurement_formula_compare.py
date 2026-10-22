"""Phase 0 — compare target, legacy SQL transcription, and decision_rules.evaluate.

Does not open a database and does not change production quantity code.
Legacy numbers are a transcription. The SQL text checks below only prove the
clauses exist in order_local.sql and in Form1.FetchSourceData.
"""

import os
import sys
from datetime import timedelta

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement import decision_rules as rules  # noqa: E402

from procurement_formula_compare import (  # noqa: E402
    AS_OF,
    VB_FORM1_RECENCY_DAYS,
    cases,
    legacy_order_local,
    legacy_vb_form1,
    target_formula,
)


def _nexora(case):
    sale_unit = case["sale_unit"] if case["sale_unit"] else 0
    src = {
        "is_active": True,
        "dont_consider": case["dont_consider"],
        "window_sales_qty": case["window_sales_qty"],
        "max_day_sale_qty": case["max_day_qty"],
        "max_bill_qty": case["max_bill_qty"],
        "max_line_sale_qty": case["max_line_qty"],
        "billing_frequency": case["bill_frequency"],
        "current_stock": case["nexora_stock"],
        "pending_receivable": case["confirmed_pending"],
        "in_transit": 0.0,
        "reserved": 0.0,
        "sale_unit": sale_unit,
        "last_sale_date": case["last_sale"],
        "last_received_date": case["last_received"],
    }
    params = rules.DecisionParameters(
        rolling_days=90,
        min_days=13,
        max_days=18,
        recency_days=case["recency_days"],
        as_of=AS_OF,
    )
    return rules.evaluate(src, params)


def _by_name():
    return {case["name"]: case for case in cases()}


def test_sql_text_matches_transcription_clauses():
    sql_path = os.path.join(
        _REPO_ROOT, "backend", "modules", "legacy_order", "sql", "order_local.sql"
    )
    sql = open(sql_path, encoding="utf-8").read()
    for fragment in (
        "COUNT(DISTINCT ps.ID) AS Frequence",
        "MAX(Quantity) AS MaxSalesQtyInBill",
        "CEILING((sq.slsqty / 90.0) * @maxday)",
        "CEILING((sq.slsqty / 90.0) * @minday)",
        "DontConsiderInOrder = 0",
        "DATEADD(day, 0 - @recencydays, GETDATE())",
        "'Additional Row'",
        "p.TotalStock",
    ):
        assert fragment in sql, fragment

    process = open(
        os.path.join(_REPO_ROOT, "backend", "modules", "legacy_order", "order_process.py"),
        encoding="utf-8",
    ).read()
    assert "WantedType = 'Additional Row'" in process
    assert "OrderQty = 0" in process

    form = open(
        r"D:\VBDOTNET\OrderManagement\OrderManagement\Form1.vb",
        encoding="utf-8",
    ).read()
    assert "DATEADD(day, -10, GETDATE())" in form
    assert "FetchSourceData" in form


def test_spike_day_bill_three_way():
    case = _by_name()["spike_day_bill"]
    legacy = legacy_order_local(case, case["recency_days"])
    target = target_formula(case)
    nexora = _nexora(case)
    assert legacy["orderable_packs"] == 1
    assert legacy["reason"] == "MAIN_LINE"
    assert target["packs"] == 5 and target["auto_order"] is True
    assert nexora["suggested_qty"] == 5
    assert nexora["procurement_action"] == rules.ACTION_INCLUDE


def test_average_bill_changes_only_the_target():
    case = _by_name()["avg_bill_binds"]
    assert legacy_order_local(case, 15)["orderable_packs"] == 1
    assert _nexora(case)["suggested_qty"] == 1
    assert target_formula(case)["packs"] == 2


def test_pending_is_not_applied_the_same_way():
    case = _by_name()["pending_20"]
    assert legacy_order_local(case, 15)["orderable_packs"] == 1
    assert target_formula(case)["packs"] == 3
    nexora = _nexora(case)
    assert nexora["procurement_action"] == rules.ACTION_EXCLUDE
    assert nexora["reason_code"] == rules.EXCLUDED_ADEQUATE_COVER
    assert nexora["suggested_qty"] == 0


def test_sale_unit_zero_and_null_block_only_the_target():
    for name in ("sale_unit_zero", "sale_unit_null"):
        case = _by_name()[name]
        legacy = legacy_order_local(case, 15)
        assert legacy["orderable_packs"] == 0
        assert legacy["reason"] == "EXCLUDED_SALE_UNIT"
        assert target_formula(case)["reason"] == "BLOCKED_SALE_UNIT"
        assert target_formula(case)["packs"] is None
        nexora = _nexora(case)
        assert nexora["procurement_action"] == rules.ACTION_INCLUDE
        assert nexora["suggested_qty"] == 50


def test_zero_sales_and_old_recency_exclude_all_three():
    zero = _by_name()["zero_sales"]
    assert legacy_order_local(zero, 15)["reason"] == "EXCLUDED_NO_ELIGIBLE_SALES"
    assert target_formula(zero)["reason"] == "EXCLUDED_NO_SALES"
    assert _nexora(zero)["reason_code"] == rules.EXCLUDED_NOT_SELLING

    old = _by_name()["recency_20_days"]
    assert legacy_order_local(old, 15)["reason"] == "EXCLUDED_RECENCY"
    assert legacy_vb_form1(old)["reason"] == "EXCLUDED_RECENCY"
    assert target_formula(old)["reason"] == "REVIEW_RECENCY"
    assert _nexora(old)["reason_code"] == rules.EXCLUDED_STALE_SALE


def test_sale_12_days_ago_splits_vb_hardcoded_recency():
    case = _by_name()["recency_12_days"]
    assert legacy_order_local(case, 15)["orderable_packs"] == 1
    assert legacy_vb_form1(case)["reason"] == "EXCLUDED_RECENCY"
    assert legacy_vb_form1(case)["recency_days_applied"] == VB_FORM1_RECENCY_DAYS
    assert target_formula(case)["packs"] == 5
    assert _nexora(case)["suggested_qty"] == 5
    # Nexora's own default parameter is 10, which would exclude this sale.
    forced = rules.evaluate(
        {
            "is_active": True,
            "dont_consider": False,
            "window_sales_qty": case["window_sales_qty"],
            "max_day_sale_qty": case["max_day_qty"],
            "max_bill_qty": case["max_bill_qty"],
            "max_line_sale_qty": case["max_line_qty"],
            "billing_frequency": case["bill_frequency"],
            "current_stock": case["nexora_stock"],
            "sale_unit": case["sale_unit"],
            "last_sale_date": case["last_sale"],
            "last_received_date": case["last_received"],
        },
        rules.DecisionParameters(
            rolling_days=90, min_days=13, max_days=18, as_of=AS_OF
        ),
    )
    assert forced["reason_code"] == rules.EXCLUDED_STALE_SALE


def test_stock_column_split_is_visible_when_inputs_differ():
    case = _by_name()["stock_source_split"]
    assert legacy_order_local(case, 15)["orderable_packs"] == 0
    assert target_formula(case)["packs"] == 1
    assert _nexora(case)["suggested_qty"] == 3


def test_rare_mover_target_holds_one_pack_for_review():
    case = _by_name()["rare_mover"]
    legacy = legacy_order_local(case, 15)
    assert legacy["sql_insert_packs"] == 1
    assert legacy["orderable_packs"] == 0
    assert legacy["reason"] == "ADDITIONAL_ROW_ZEROED"
    target = target_formula(case)
    assert target["packs"] == 1
    assert target["auto_order"] is False
    assert target["reason"] == "RARE_MOVING_MANUAL_REVIEW"
    nexora = _nexora(case)
    assert nexora["suggested_qty"] == 1
    assert nexora["reason_code"] == rules.INCLUDED_RARE_MOVER_TOPUP


def test_dont_consider_product_flag_is_not_a_legacy_sql_gate():
    cleared = _by_name()["dont_consider"]
    assert target_formula(cleared)["reason"] == "EXCLUDED_DONT_CONSIDER"
    assert _nexora(cleared)["reason_code"] == rules.EXCLUDED_FLAGGED
    assert legacy_order_local(cleared, 15)["reason"] == "EXCLUDED_NO_ELIGIBLE_SALES"

    flagged_with_sales = _by_name()["dont_consider_flag_only"]
    assert legacy_order_local(flagged_with_sales, 15)["orderable_packs"] == 1
    assert target_formula(flagged_with_sales)["reason"] == "EXCLUDED_DONT_CONSIDER"
    assert _nexora(flagged_with_sales)["reason_code"] == rules.EXCLUDED_FLAGGED


def test_same_day_calendar_total_is_an_explicit_assumption():
    case = _by_name()["same_day_two_bills"]
    assert case["max_day_qty"] == 80
    assert case["max_day_if_time_splits"] == 40
    assert legacy_order_local(case, 15)["orderable_packs"] == 1
    assert target_formula(case)["packs"] == 5
    assert _nexora(case)["suggested_qty"] == 5
    split = dict(case)
    split["max_day_qty"] = case["max_day_if_time_splits"]
    # Legacy OrderQty does not read max day, so a time-split does not change it.
    assert legacy_order_local(split, 15)["orderable_packs"] == 1
    assert _nexora(split)["suggested_qty"] == 1


def test_line_frequency_versus_bill_frequency():
    case = _by_name()["line_vs_bill_frequency"]
    assert legacy_order_local(case, 15)["orderable_packs"] == 1
    assert target_formula(case)["packs"] == 6
    assert _nexora(case)["suggested_qty"] == 6


def test_every_case_records_all_three_results():
    names = []
    for case in cases():
        names.append(case["name"])
        legacy_order_local(case, case["recency_days"])
        legacy_vb_form1(case)
        target_formula(case)
        _nexora(case)
    assert len(names) == len(set(names)) == 14


def test_recency_boundary_keeps_a_sale_exactly_15_days_old():
    case = dict(_by_name()["spike_day_bill"])
    case["last_sale"] = AS_OF - timedelta(days=15)
    assert legacy_order_local(case, 15)["reason"] == "MAIN_LINE"
    assert target_formula(case)["reason"] == "AUTO"
    assert _nexora(case)["procurement_action"] == rules.ACTION_INCLUDE
