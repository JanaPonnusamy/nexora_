"""Phase 0 formula comparison. Test-only. Not used by order generation.

Three pure functions, same synthetic inputs:

* target_formula — agreed Procurement Workspace rules (2026-10-19 master prompt)
* legacy_order_local — transcription of order_local.sql plus the post-insert
  Additional Row zeroing in order_process.py. This does not execute SQL Server.
* VB Form1.FetchSourceData is the same arithmetic with recency hard-coded at
  10 days. legacy_vb_form1 applies that one difference.

Nexora output is decision_rules.evaluate, called by the test, not reimplemented
here.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta


AS_OF = datetime(2026, 10, 19, 12, 0, 0)
WINDOW_DAYS = 90
MIN_DAYS = 13
MAX_DAYS = 18
TARGET_RECENCY_DAYS = 15
VB_FORM1_RECENCY_DAYS = 10


def _ceil(value):
    """SQL CEILING for non-negative demand figures."""
    return int(math.ceil(value or 0))


def _days_ago(days):
    return AS_OF - timedelta(days=days)


def legacy_bounds(window_qty, line_frequency, max_line_qty, min_days=MIN_DAYS, max_days=MAX_DAYS):
    """minqty / maxqty from the local SQL CASE. Frequency is COUNT(DISTINCT ID)."""
    avg_days_min = _ceil((window_qty / 90.0) * min_days) if window_qty else 0
    avg_days_max = _ceil((window_qty / 90.0) * max_days) if window_qty else 0
    per_line = _ceil(window_qty / line_frequency) if line_frequency else 0
    min_qty = max(avg_days_min, per_line)
    max_qty = max(avg_days_max, _ceil(max_line_qty or 0))
    return min_qty, max_qty


def _rare_predicate(stock, min_qty, line_frequency, window_qty, last_sale, last_received):
    sold_after_receipt = (
        last_sale is not None
        and last_received is not None
        and last_sale > last_received
    )
    return (
        stock <= 1
        and min_qty <= 1
        and line_frequency > 1
        and window_qty > 1
        and sold_after_receipt
    )


def legacy_order_local(case, recency_days):
    """order_local.sql main branch + Additional Row union, then the zeroing update.

    Returns the quantity a buyer would see on Qty Check (status 0), which is 0
    for Additional Row after order_process.py sets Status = 2 and OrderQty = 0.
    sql_insert_packs is the quantity the SELECT emits before that update.
    """
    window = case["window_sales_qty"]
    stock = case["total_stock"]
    sale_unit = case["sale_unit"]
    last_sale = case["last_sale"]
    last_received = case["last_received"]
    # The sales CTE drops DontConsiderInOrder lines before this SELECT.
    # A product-level flag with sales still in the window is not a SQL gate.
    # Callers that mean "those lines were excluded" pass window_sales_qty 0.
    if window <= 0 or last_sale is None:
        return _legacy_out("EXCLUDED_NO_ELIGIBLE_SALES", 0, 0)

    min_qty, max_qty = legacy_bounds(
        window, case["line_frequency"], case["max_line_qty"]
    )
    recent = last_sale >= _days_ago(recency_days)
    sold_since_receipt = last_received is None or last_sale >= last_received
    unit_ok = sale_unit is not None and sale_unit > 0
    cover_gap = ((max_qty - stock) / sale_unit) > 0 if unit_ok else False
    main = recent and sold_since_receipt and min_qty > stock and cover_gap

    sql_packs = 0
    if main:
        if stock == 0 and (max_qty - stock) <= 0:
            sql_packs = 1
        elif unit_ok:
            sql_packs = _ceil((max_qty - stock) / sale_unit)
        else:
            sql_packs = 0
        return {
            "reason": "MAIN_LINE",
            "orderable_packs": sql_packs,
            "sql_insert_packs": sql_packs,
            "auto_order": sql_packs > 0,
        }

    if recent and _rare_predicate(
        stock, min_qty, case["line_frequency"], window, last_sale, last_received
    ):
        return {
            "reason": "ADDITIONAL_ROW_ZEROED",
            "orderable_packs": 0,
            "sql_insert_packs": 1,
            "auto_order": False,
        }
    if not recent:
        reason = "EXCLUDED_RECENCY"
    elif not sold_since_receipt:
        reason = "EXCLUDED_NO_SALE_SINCE_RECEIPT"
    elif not unit_ok:
        reason = "EXCLUDED_SALE_UNIT"
    else:
        reason = "EXCLUDED_COVER"
    return _legacy_out(reason, 0, 0)


def legacy_vb_form1(case):
    """FetchSourceData local branch: same math, recency fixed at 10 days."""
    out = legacy_order_local(case, VB_FORM1_RECENCY_DAYS)
    out["recency_days_applied"] = VB_FORM1_RECENCY_DAYS
    return out


def _legacy_out(reason, orderable, sql_packs):
    return {
        "reason": reason,
        "orderable_packs": orderable,
        "sql_insert_packs": sql_packs,
        "auto_order": False,
    }


def target_formula(case):
    """Agreed target. Recency is always 15 days. Stock is TotalStock.

    Confirmed supplier pending is subtracted from net demand only. It is not
    added to stock for the eligibility test. SaleUnit null/<=0 blocks auto qty.
    Rare movers that miss the positive-net list are suggested at 1 pack for
    review and are not auto-orderable.
    """
    sale_unit = case["sale_unit"]
    if sale_unit is None or sale_unit <= 0:
        return _target("BLOCKED_SALE_UNIT", None, False)
    if case["dont_consider"]:
        return _target("EXCLUDED_DONT_CONSIDER", 0, False)
    window = case["window_sales_qty"]
    if window <= 0:
        return _target("EXCLUDED_NO_SALES", 0, False)
    last_sale = case["last_sale"]
    if last_sale is None or last_sale < _days_ago(TARGET_RECENCY_DAYS):
        return _target("REVIEW_RECENCY", 0, False)
    last_received = case["last_received"]
    if last_received is not None and last_sale < last_received:
        return _target("SUPPRESSED_NO_SALE_SINCE_RECEIPT", 0, False)

    avg_daily = window / float(WINDOW_DAYS)
    bill_frequency = case["bill_frequency"]
    avg_bill = (window / bill_frequency) if bill_frequency else 0
    gross = max(avg_daily * MAX_DAYS, case["max_bill_qty"], case["max_day_qty"], avg_bill)
    net = gross - case["total_stock"] - case["confirmed_pending"]
    min_qty, _max_qty = legacy_bounds(
        window, case["line_frequency"], case["max_line_qty"]
    )
    if net <= 0:
        if _rare_predicate(
            case["total_stock"], min_qty, case["line_frequency"], window,
            last_sale, last_received,
        ):
            return _target("RARE_MOVING_MANUAL_REVIEW", 1, False)
        return _target("ZERO_NET", 0, False)
    packs = _ceil(net / sale_unit)
    if packs <= 0:
        return _target("ZERO_NET", 0, False)
    return _target("AUTO", packs, True)


def _target(reason, packs, auto_order):
    return {"reason": reason, "packs": packs, "auto_order": auto_order}


def cases():
    """Synthetic rows. transactionvalidity mapping is not encoded.

    max_day_qty is the calendar-day sum. The VB max-day query groups the raw
    Transactiondate value; if that column contains a time, one calendar day
    can split. That split is recorded on the same-day case and is UNKNOWN
    against live data.
    """
    recent = _days_ago(2)
    old_receipt = _days_ago(40)
    base = {
        "dont_consider": False,
        "window_sales_qty": 180.0,
        "line_frequency": 4,
        "bill_frequency": 4,
        "max_line_qty": 20.0,
        "max_bill_qty": 60.0,
        "max_day_qty": 80.0,
        "total_stock": 30.0,
        "nexora_stock": 30.0,
        "confirmed_pending": 0.0,
        "sale_unit": 10.0,
        "last_sale": recent,
        "last_received": old_receipt,
        "recency_days": TARGET_RECENCY_DAYS,
    }

    def row(name, **overrides):
        item = dict(base)
        item["name"] = name
        item.update(overrides)
        return item

    return [
        row("spike_day_bill"),
        row(
            "avg_bill_binds",
            max_line_qty=20.0,
            max_bill_qty=20.0,
            max_day_qty=20.0,
        ),
        row("pending_20", confirmed_pending=20.0),
        row("sale_unit_zero", sale_unit=0),
        row("sale_unit_null", sale_unit=None),
        row("zero_sales", window_sales_qty=0),
        row("recency_20_days", last_sale=_days_ago(20)),
        row("recency_12_days", last_sale=_days_ago(12)),
        row(
            "stock_source_split",
            total_stock=40.0,
            nexora_stock=10.0,
            max_day_qty=20.0,
            max_bill_qty=20.0,
            max_line_qty=20.0,
        ),
        row(
            "rare_mover",
            window_sales_qty=3.0,
            line_frequency=3,
            bill_frequency=3,
            max_line_qty=1.0,
            max_bill_qty=1.0,
            max_day_qty=1.0,
            total_stock=1.0,
            nexora_stock=1.0,
            sale_unit=10.0,
        ),
        row("dont_consider", dont_consider=True, window_sales_qty=0),
        row(
            "dont_consider_flag_only",
            dont_consider=True,
            window_sales_qty=180.0,
        ),
        row(
            "same_day_two_bills",
            max_day_qty=80.0,
            max_day_if_time_splits=40.0,
            max_bill_qty=40.0,
            max_line_qty=40.0,
        ),
        row(
            "line_vs_bill_frequency",
            line_frequency=6,
            bill_frequency=1,
            window_sales_qty=60.0,
            max_line_qty=10.0,
            max_bill_qty=60.0,
            max_day_qty=60.0,
            total_stock=5.0,
            nexora_stock=5.0,
        ),
    ]
