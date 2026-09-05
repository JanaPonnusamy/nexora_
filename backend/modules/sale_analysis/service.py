"""Sale Analysis service — window resolution + the stock-vs-sales arithmetic.

Given a report window (this month / last 30 days / an explicit range) and a
target cover period (in days), it turns the raw per-product numbers into the
grouped ``summary + detail`` shape the frontend renders and exports:

    Stock, Sale (window), Stock Cover Days, Excess Stock,
    Stock Cost, Sales Cost, Excess Stock Cost

Definitions (per product; a group aggregates the sums):
    avg daily sale = SaleQty / window_days
    stock cover days = Stock / avg daily sale          (blank when nothing sold)
    excess stock = max(Stock - avg daily sale * target_days, 0)
    stock cost   = Stock * PTR
    sales cost   = cost of goods sold in the window
    excess cost  = excess stock * PTR
"""

import math
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException

from modules.sale_analysis import repository as repo

_MONEY, _INT = "money", "int"

# Ordered column metadata shared by summary + detail. ``Name`` holds the group
# name on a summary row and the product name on a detail row.
_COLUMNS = [
    ("Name", "Product / Group", "left", None),
    ("Stock", "Stock", "right", _INT),
    ("SaleQty", "Sale", "right", _INT),
    ("CoverDays", "Cover Days", "right", _INT),
    ("Excess", "Excess Stock", "right", _INT),
    ("StockCost", "Stock Cost", "right", _MONEY),
    ("SalesCost", "Sales Cost", "right", _MONEY),
    ("ExcessCost", "Excess Stock Cost", "right", _MONEY),
]

_WINDOWS = ("month", "last30", "range")


def columns():
    return [{"key": k, "label": lbl, "align": al, "format": fmt}
            for (k, lbl, al, fmt) in _COLUMNS]


# --- window ---------------------------------------------------------------

def _resolve_window(window, from_date, to_date):
    window = (window or "month").lower()
    if window not in _WINDOWS:
        raise HTTPException(status_code=400, detail=f"bad window '{window}'")
    today = date.today()
    if window == "month":
        start = today.replace(day=1)
        end = today
        label = "This month"
    elif window == "last30":
        start = today - timedelta(days=29)
        end = today
        label = "Last 30 days"
    else:
        if not (from_date and to_date):
            raise HTTPException(status_code=400, detail="from and to are required for a custom range")
        try:
            start = date.fromisoformat(str(from_date)[:10])
            end = date.fromisoformat(str(to_date)[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="from/to must be YYYY-MM-DD dates")
        if end < start:
            raise HTTPException(status_code=400, detail="'to' cannot be before 'from'")
        label = f"{start.isoformat()} → {end.isoformat()}"
    window_days = (end - start).days + 1  # inclusive
    return start, end, max(window_days, 1), label


# --- metric arithmetic ----------------------------------------------------

def _dec(v):
    return Decimal(str(v)) if v is not None else Decimal(0)


def _enrich(raw, window_days, target_days):
    """Turn one raw product row into the full metric row."""
    stock = _dec(raw.get("Stock"))
    sale_qty = _dec(raw.get("SaleQty"))
    ptr = _dec(raw.get("PTR"))
    sales_cost = _dec(raw.get("SalesCost"))
    # PurchasePrice (PTR) is per SALE UNIT (pack), while Stock/SaleQty are in
    # individual pieces — so value stock at the per-piece cost (PTR / SaleUnit).
    # This matches SalesCost, which already comes from the sales table's actual
    # per-piece CostOfSales. Without this, stock/excess cost is inflated by the
    # pack size (e.g. ×10 for a "…10" pack).
    sale_unit = _dec(raw.get("SaleUnit"))
    if sale_unit <= 0:
        sale_unit = Decimal(1)
    unit_cost = ptr / sale_unit

    avg_daily = sale_qty / Decimal(window_days) if window_days else Decimal(0)
    needed = avg_daily * Decimal(target_days)
    excess = stock - needed
    if excess < 0:
        excess = Decimal(0)
    cover = (stock / avg_daily) if avg_daily > 0 else None

    return {
        "ProductCode": raw.get("ProductCode"),
        "Name": raw.get("ProductName"),
        "Stock": _round(stock),
        "SaleQty": _round(sale_qty),
        "CoverDays": (math.ceil(float(cover)) if cover is not None else None),
        "Excess": _round(excess),
        "StockCost": _round(stock * unit_cost, 2),
        "SalesCost": _round(sales_cost, 2),
        "ExcessCost": _round(excess * unit_cost, 2),
    }


def _round(v, places=0):
    q = Decimal(1) if places == 0 else Decimal(10) ** -places
    r = _dec(v).quantize(q)
    return int(r) if places == 0 else float(r)


def _summary(name, rows, window_days):
    stock = sum(_dec(r["Stock"]) for r in rows)
    sale = sum(_dec(r["SaleQty"]) for r in rows)
    avg_daily = sale / Decimal(window_days) if window_days else Decimal(0)
    cover = (stock / avg_daily) if avg_daily > 0 else None
    return {
        "Name": name,
        "Stock": int(stock),
        "SaleQty": int(sale),
        "CoverDays": (math.ceil(float(cover)) if cover is not None else None),
        "Excess": int(sum(_dec(r["Excess"]) for r in rows)),
        "StockCost": float(sum(_dec(r["StockCost"]) for r in rows)),
        "SalesCost": float(sum(_dec(r["SalesCost"]) for r in rows)),
        "ExcessCost": float(sum(_dec(r["ExcessCost"]) for r in rows)),
    }


# --- public API -----------------------------------------------------------

def run(tenant_id, store_id, group_ids, adhoc_codes, window, from_date, to_date, target_days):
    if not tenant_id or not store_id:
        raise HTTPException(status_code=400, detail="tenant_id and store_id are required")
    try:
        target_days = int(target_days)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="target_days must be an integer")
    if target_days <= 0:
        target_days = 30

    start, end, window_days, label = _resolve_window(window, from_date, to_date)

    # Build the list of (group_id, name, [product_names]) buckets to report on.
    buckets = []
    for gid in (group_ids or []):
        g = repo.get_group(tenant_id, gid)
        if g:
            buckets.append((g["group_id"], g["group_name"], g["product_names"]))
    if adhoc_codes:
        names = [c.strip() for c in adhoc_codes if str(c).strip()]
        if names:
            buckets.append((None, "Ad-hoc selection", names))

    if not buckets:
        raise HTTPException(status_code=400, detail="select at least one saved group or provide product names")

    groups = []
    all_rows = []
    for gid, gname, names in buckets:
        raw = repo.product_metrics(tenant_id, store_id, names, start, end)
        rows = [_enrich(r, window_days, target_days) for r in raw]
        all_rows.extend(rows)
        groups.append({
            "group_id": gid,
            "group_name": gname,
            "summary": _summary(gname, rows, window_days),
            "rows": rows,
        })

    grand = _summary("All groups", all_rows, window_days) if len(groups) > 1 else None

    return {
        "window_label": label,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "window_days": window_days,
        "target_days": target_days,
        "columns": columns(),
        "groups": groups,
        "grand_summary": grand,
    }
