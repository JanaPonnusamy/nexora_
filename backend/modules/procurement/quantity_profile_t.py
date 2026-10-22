"""Profile T quantity suggestion. Not wired into decision_rules.evaluate.

This is the owner-confirmed target from
docs/procurement-workspace-unification/contracts/Procurement_Workspace_Master_Phase_Prompts.md.
Callers must opt in. The live Purchase Manager engine stays decision_rules.evaluate.

Confirmed supplier pending is a caller-supplied number. This module does not
choose a database column for it. transactionvalidity is not interpreted.
"""

from __future__ import annotations

import math
from datetime import timedelta

PROFILE_ID = "T"
WINDOW_DAYS = 90
MIN_DAYS = 13
MAX_DAYS = 18
RECENCY_DAYS = 15
RARE_MOVING_WARNING = "RARE MOVING — MANUAL REVIEW REQUIRED"


def _ceil(value):
    return int(math.ceil(value or 0))


def _min_qty(window_qty, line_frequency):
    """Legacy additional-row floor: MAX(CEIL(avg*minDays), CEIL(qty/line frequency))."""
    by_days = _ceil((window_qty / 90.0) * MIN_DAYS) if window_qty else 0
    by_line = _ceil(window_qty / line_frequency) if line_frequency else 0
    return max(by_days, by_line)


def _rare_mover(stock, min_qty, line_frequency, window_qty, last_sale, last_received):
    sold_after_receipt = (
        last_sale is not None
        and last_received is not None
        and last_sale > last_received
    )
    return (
        stock <= 1
        and min_qty <= 1
        and (line_frequency or 0) > 1
        and window_qty > 1
        and sold_after_receipt
    )


def evaluate_profile_t(case, as_of):
    """Return packs, reason, auto_order, and warning.

    case keys: window_sales_qty, bill_frequency, line_frequency, max_bill_qty,
    max_day_qty, total_stock, confirmed_pending, sale_unit, dont_consider,
    last_sale, last_received.

    max_day_qty must already be the calendar-day sum. This function does not
    decide whether Transactiondate contains a time.
    """
    sale_unit = case.get("sale_unit")
    if sale_unit is None or sale_unit <= 0:
        return _out("BLOCKED_SALE_UNIT", None, False, None)

    if case.get("dont_consider"):
        return _out("EXCLUDED_DONT_CONSIDER", 0, False, None)

    window = case.get("window_sales_qty") or 0
    if window <= 0:
        return _out("EXCLUDED_NO_SALES", 0, False, None)

    last_sale = case.get("last_sale")
    if last_sale is None or last_sale < as_of - timedelta(days=RECENCY_DAYS):
        return _out("REVIEW_RECENCY", 0, False, None)

    last_received = case.get("last_received")
    if last_received is not None and last_sale < last_received:
        return _out("SUPPRESSED_NO_SALE_SINCE_RECEIPT", 0, False, None)

    avg_daily = window / float(WINDOW_DAYS)
    bill_frequency = case.get("bill_frequency") or 0
    avg_bill = (window / bill_frequency) if bill_frequency else 0
    gross = max(
        avg_daily * MAX_DAYS,
        case.get("max_bill_qty") or 0,
        case.get("max_day_qty") or 0,
        avg_bill,
    )
    net = gross - (case.get("total_stock") or 0) - (case.get("confirmed_pending") or 0)
    if net <= 0:
        if _rare_mover(
            case.get("total_stock") or 0,
            _min_qty(window, case.get("line_frequency") or 0),
            case.get("line_frequency") or 0,
            window,
            last_sale,
            last_received,
        ):
            return _out("RARE_MOVING_MANUAL_REVIEW", 1, False, RARE_MOVING_WARNING)
        return _out("ZERO_NET", 0, False, None)

    packs = _ceil(net / sale_unit)
    if packs <= 0:
        return _out("ZERO_NET", 0, False, None)
    return _out("AUTO", packs, True, None)


def _out(reason, packs, auto_order, warning):
    return {
        "profile": PROFILE_ID,
        "reason": reason,
        "packs": packs,
        "auto_order": auto_order,
        "warning": warning,
    }
