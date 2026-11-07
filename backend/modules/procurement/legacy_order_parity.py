"""Buyer-visible order quantity from the legacy order SQL.

This is the generation profile for procurement refresh. It transcribes
``order_local.sql``, ``order_remote.sql``, and ``order_warehouse.sql``
plus the Additional Row zeroing in ``order_process.insert_data_into_destination``.
It does not execute SQL Server.

The three modes are not the same. Quantity rounding matches local and
warehouse (``NULLIF`` on SaleUnit, pack ceiling). Remote divides by
``SaleUnit`` with no ``NULLIF`` and reads the spike off ``Transactiondate > @ODATA``
rather than ``>=``. Warehouse quantity math matches local; its demand
includes Transfer-Out and its watermarks come from a different source.
Callers pass aggregates already computed the way that mode's SQL does.

Confirmed supplier pending, in-transit, and reserved quantities do not
appear in any of the three order queries. They are not subtracted here.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

PROFILE_LEGACY_LOCAL = "legacy_local"
PROFILE_NEXORA = "nexora"
WINDOW_DAYS = 90


class LegacyRemoteQueryError(Exception):
    """order_remote.sql divides by SaleUnit. SaleUnit 0 aborts that statement."""


def generation_profile():
    """Default is the legacy local order query. Set PROCUREMENT_GENERATION_PROFILE=nexora to restore decision_rules.evaluate."""
    raw = os.environ.get("PROCUREMENT_GENERATION_PROFILE", PROFILE_LEGACY_LOCAL)
    return (raw or PROFILE_LEGACY_LOCAL).strip().lower()


def bound_recency_days():
    """Same default the legacy order job binds (@recencydays)."""
    raw = os.getenv("LEGACY_RECENCY_DAYS", "15")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return 15
    return days if days > 0 else 15


def _ceil(value):
    return int(math.ceil(value))


def _present(case, key):
    return key in case and case[key] is not None


def min_qty(window_qty, line_frequency, min_days):
    """order_*.sql minqty CASE. Frequency is COUNT(DISTINCT ProductSaleInformation.ID)."""
    by_days = _ceil((window_qty / 90.0) * min_days) if window_qty else 0
    if not line_frequency:
        return by_days
    by_line = _ceil(window_qty / line_frequency)
    if by_days < by_line:
        return by_line
    return by_days


def max_qty(window_qty, max_line_qty, max_days):
    """order_*.sql maxqty CASE. max_line_qty is MAX(single-row Quantity), not a day or bill sum.

    A missing spike (LEFT JOIN miss) makes the comparison UNKNOWN, so the
    ELSE branch keeps the days ceiling. The spike itself is not re-ceiled.
    """
    by_days = _ceil((window_qty / 90.0) * max_days) if window_qty else 0
    if max_line_qty is None:
        return by_days
    if by_days < max_line_qty:
        return max_line_qty
    return by_days


def _unit_ratio(max_quantity, stock, sale_unit, mode):
    """(maxqty - TotalStock) / SaleUnit, with each mode's NULL/zero behavior."""
    if stock is None or max_quantity is None:
        return None
    gap = max_quantity - stock
    if mode == "remote":
        if sale_unit == 0:
            raise LegacyRemoteQueryError(
                "order_remote.sql divides by SaleUnit with no NULLIF; SaleUnit 0 aborts the query"
            )
        if sale_unit is None:
            return None
        return gap / sale_unit
    if sale_unit is None or sale_unit == 0:
        return None
    return gap / sale_unit


def _sql_packs(stock, max_quantity, sale_unit, mode):
    """Orderqty CASE. Only meaningful for a row that already passed the main WHERE."""
    gap = (max_quantity if max_quantity is not None else 0) - (stock or 0)
    if mode == "remote":
        if sale_unit is None or sale_unit == 0:
            raise LegacyRemoteQueryError(
                "order_remote.sql divides by SaleUnit with no NULLIF; SaleUnit 0 aborts the query"
            )
        packs = _ceil(gap / sale_unit)
        if stock == 0 and packs == 0:
            return 1
        return packs
    if stock == 0 and gap <= 0:
        return 1
    if sale_unit is not None and sale_unit > 0:
        return _ceil(gap / sale_unit)
    return 0


def buyer_result(case, *, mode, min_days, max_days, recency_days, as_of):
    """Packs a buyer sees after Additional Row zeroing.

    ``mode`` is ``local``, ``remote``, or ``warehouse``. Warehouse pack math
    matches local. ``max_line_qty`` must already use that mode's date bound
    (local/warehouse ``>= @ODATA``, remote ``> @ODATA``).

    Returns orderable_packs (0 after the process update for Additional Row),
    sql_insert_packs (1 for that row before the update), reason, and auto_order.
    """
    if mode not in ("local", "remote", "warehouse"):
        raise ValueError(f"unknown order mode: {mode}")
    pack_mode = "local" if mode == "warehouse" else mode
    window = float(case["window_sales_qty"] or 0)
    if window <= 0 or not _present(case, "last_sale"):
        return _out("EXCLUDED_NO_ELIGIBLE_SALES", 0, 0, False)

    frequency = int(case.get("line_frequency") or 0)
    max_line = float(case["max_line_qty"]) if _present(case, "max_line_qty") else None
    stock = float(case["total_stock"]) if _present(case, "total_stock") else None
    sale_unit = float(case["sale_unit"]) if _present(case, "sale_unit") else None
    last_sale = case["last_sale"]
    last_received = case["last_received"] if _present(case, "last_received") else None
    floor = min_qty(window, frequency, min_days)
    ceiling = max_qty(window, max_line, max_days)
    cutoff = as_of - timedelta(days=recency_days)
    recent = last_sale >= cutoff

    ratio = _unit_ratio(ceiling, stock, sale_unit, pack_mode)
    qty_pred = (
        ratio is not None
        and ratio > 0
        and stock is not None
        and floor > stock
    )
    sold_since_receipt = (
        last_received is not None and last_sale >= last_received
    )
    main = recent and qty_pred and sold_since_receipt

    if main:
        packs = _sql_packs(stock, ceiling, sale_unit, pack_mode)
        return _out("MAIN_LINE", packs, packs, packs > 0, floor, ceiling)

    additional = (
        stock is not None
        and stock <= 1
        and floor <= 1
        and frequency > 1
        and window > 1
        and recent
        and last_received is not None
        and last_sale > last_received
        and not qty_pred
    )
    if additional:
        # order_process sets OrderQty = 0 and Status = 2 for WantedType Additional Row.
        return _out("ADDITIONAL_ROW_ZEROED", 0, 1, False, floor, ceiling)
    if not recent:
        reason = "EXCLUDED_RECENCY"
    elif last_received is None or not sold_since_receipt:
        reason = "EXCLUDED_NO_SALE_SINCE_RECEIPT"
    elif ratio is None:
        reason = "EXCLUDED_SALE_UNIT"
    else:
        reason = "EXCLUDED_COVER"
    return _out(reason, 0, 0, False, floor, ceiling)


def _out(reason, orderable, sql_packs, auto_order, floor=None, ceiling=None):
    return {
        "reason": reason,
        "orderable_packs": orderable,
        "sql_insert_packs": sql_packs,
        "auto_order": auto_order,
        "min_qty": floor,
        "max_qty": ceiling,
    }


def evaluate_for_vpl(src, params, mode="local"):
    """Map one load_source row into VPL columns using the legacy local profile.

    Additional Row stays on the VPL at suggested quantity 0 (the buyer-visible
    quantity). Working-order generation keeps only suggested_qty > 0, so those
    rows are not ordered. Pending quantities are recorded as 0 because the
    legacy order query has no pending term.
    """
    as_of = params.as_of or datetime.now()
    case = {
        "window_sales_qty": src.get("legacy_window_sales_qty", src.get("window_sales_qty")),
        "line_frequency": src.get("legacy_line_frequency", src.get("line_frequency")),
        "max_line_qty": src.get("legacy_max_line_qty", src.get("max_line_qty", src.get("max_line_sale_qty"))),
        "total_stock": src.get("total_stock", src.get("current_stock")),
        "sale_unit": src.get("sale_unit"),
        "last_sale": src.get("legacy_last_sale_date", src.get("last_sale_date", src.get("last_sale"))),
        "last_received": src.get("legacy_last_received_date", src.get("last_received_date", src.get("last_received"))),
    }
    # A loader that has not been given a legacy spike leaves the key absent
    # (UNKNOWN → days ceiling). An explicit 0 is a real MAX of zero.
    if "legacy_max_line_qty" not in src and "max_line_qty" not in src and "max_line_sale_qty" not in src:
        case["max_line_qty"] = None
    result = buyer_result(
        case,
        mode=mode,
        min_days=params.min_days,
        max_days=params.max_days,
        recency_days=params.recency_days,
        as_of=as_of,
    )
    window = float(case["window_sales_qty"] or 0)
    stock = float(case["total_stock"]) if _present(case, "total_stock") else 0.0
    avg = (window / float(WINDOW_DAYS)) if window else 0.0
    included = result["reason"] in ("MAIN_LINE", "ADDITIONAL_ROW_ZEROED")
    packs = int(result["orderable_packs"] or 0)
    max_line = case["max_line_qty"]
    return {
        "avg_daily_sales": avg,
        "window_sales_qty": window,
        "max_day_sale_qty": src.get("max_day_sale_qty") or 0,
        "max_bill_qty": src.get("max_bill_qty") or 0,
        "billing_frequency": src.get("legacy_line_frequency", src.get("line_frequency")) or 0,
        "current_stock_qty": stock,
        "available_stock_qty": stock,
        "pending_purchase_qty": 0,
        "pending_sales_qty": 0,
        "days_cover": (stock / avg) if avg else 0.0,
        "movement_class": None,
        "stock_status": None,
        "effective_available_qty": stock,
        "pending_used_qty": 0,
        "target_days": params.max_days,
        "target_stock_qty": result["max_qty"],
        "raw_required_qty": None if result["max_qty"] is None else result["max_qty"] - stock,
        "required_qty": packs,
        "suggested_qty": packs,
        "final_required_qty": packs,
        "procurement_action": "INCLUDE" if included else "EXCLUDE",
        "trigger_reason": result["reason"],
        "reason_code": result["reason"],
        "reason_text": (
            f"Legacy {mode} order: {result['reason']}; "
            f"buyer packs {packs}; SQL insert {result['sql_insert_packs']}; "
            f"minqty {result['min_qty']}; maxqty {result['max_qty']}; "
            f"max line {max_line}; TotalStock {stock}. "
            "Pending, in-transit, and reserved quantities are not in the legacy order query."
        )[:500],
    }
