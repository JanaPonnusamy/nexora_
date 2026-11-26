"""Why is this product in the order? -- the Procurement "Why ordered" card.

Explains one OrderManagement line with the quantities the Order Process
STORED for it (SLSQty, Frequence, MinQty, MaxQty, TotalStock, SaleUnit,
OrgOrderQty, WantedType) and the order header's MinDays/MaxDays, laid out as
the steps of the engine that built it:

  LEGACY (sql/order_local.sql):
    min  = MAX(CEIL(sales/90 x MinDays), CEIL(sales / sale lines))
    max  = MAX(CEIL(sales/90 x MaxDays), biggest single sale line)
    ordered when stock < min;  packs = CEIL((max - stock) / pack)
  RULEBOOK (procurement.quantity_profile_t):
    gross = MAX(avg/day x max cover, max bill, max day, avg bill)
    packs = CEIL((gross - stock) / pack)

plus the product's 90-day sales, day by day, read now from
ProductSaleInformation (same valid-line filter as the order query), so the
operator can see where the numbers came from. Read-only.
"""
import datetime
import math

from modules.legacy_order import database, rulebook_order

WINDOW_DAYS = 90

_LEGACY_REASONS = {
    "Regular Order Based Min & Max": "Stock fell below the minimum level, so it is ordered back up to the maximum level.",
    "Min & Max Based MaxsaleQTY": "Stock fell below the minimum level, and one day's sale is bigger than the usual minimum - ordered up to the maximum level.",
    "Once Sold Last 90 days": "Sold only once in 90 days; stock is below that sale's quantity.",
    "Rare Moment": "Stock is 0 and the need is less than one pack - 1 pack is ordered so the item is not out of stock.",
    "Additional Row": "Stock is 1 or less and it keeps selling (more than one sale in 90 days) - 1 pack top-up.",
}


def _num(v):
    return float(v) if v is not None else 0.0


def _fmt(v):
    v = _num(v)
    return str(int(v)) if v.is_integer() else f"{v:.2f}"


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _sales(cur, store_name, product_code, start, end):
    rows = cur.execute(
        "SELECT CAST(ps.TransactionDate AS date) AS d, RTRIM(ps.SeriesName) AS series, RTRIM(ps.Bnumber) AS bno, "
        "ps.ID, ps.Quantity, ISNULL(ps.DontConsiderInOrder, 0) AS dont "
        "FROM ProductSaleInformation ps WITH (NOLOCK) "
        "WHERE ps.StoreName = ? AND ps.ProductCode = ? AND ps.TransactionDate >= ? AND ps.TransactionDate < ? "
        "AND ps.Quantity > 0 AND ps.TransactionValidity = 0 AND ps.SeriesTransID = 1",
        store_name, product_code, start, end,
    ).fetchall()
    days, bills, bill_dates, lines = {}, {}, {}, set()
    excluded_qty = excluded_lines = max_line = 0.0
    for r in rows:
        qty = _num(r.Quantity)
        if r.dont:
            excluded_qty += qty
            excluded_lines += 1
            continue
        day = days.setdefault(r.d, {"qty": 0.0, "bills": set()})
        day["qty"] += qty
        bill = f"{r.series}|{r.bno}"
        day["bills"].add(bill)
        bills[bill] = bills.get(bill, 0.0) + qty
        bill_dates.setdefault(bill, r.d)
        lines.add(r.ID)
        max_line = max(max_line, qty)
    total = sum(d["qty"] for d in days.values())
    max_day = max(days.items(), key=lambda kv: kv[1]["qty"], default=(None, {"qty": 0.0}))
    return {
        "total_qty": total,
        "bills": len(bills),
        "sale_lines": len(lines),
        "sale_days": len(days),
        "max_line_qty": max_line,
        "max_bill_qty": max(bills.values(), default=0.0),
        "max_day_qty": max_day[1]["qty"],
        "max_day_date": _iso(max_day[0]),
        "avg_per_day": total / WINDOW_DAYS,
        "excluded_qty": excluded_qty,
        "excluded_lines": int(excluded_lines),
        "daily": [{"date": _iso(d), "qty": v["qty"], "bills": len(v["bills"])} for d, v in sorted(days.items())],
        # Biggest single bills (product qty summed per bill) -- the Procurement
        # qty warning checks a bulk sale that keeps coming back.
        "top_bills": [{"qty": q, "date": _iso(bill_dates[b])}
                      for b, q in sorted(bills.items(), key=lambda kv: -kv[1])[:10]],
    }


def _legacy_steps(o, min_days, max_days):
    sls, freq, stock, pack = _num(o.SLSQty), _num(o.Frequence), _num(o.TotalStock), _num(o.SaleUnit)
    per_day = sls / WINDOW_DAYS
    per_sale = math.ceil(sls / freq) if freq else 0
    steps = [
        {"label": "90-day sales", "formula": f"{_fmt(sls)} qty in {_fmt(freq)} sale(s)", "value": _fmt(sls)},
        {"label": "Average per day", "formula": f"{_fmt(sls)} / 90", "value": f"{per_day:.2f}"},
        {"label": "Average per sale", "formula": f"CEIL({_fmt(sls)} / {_fmt(freq)})", "value": _fmt(per_sale)},
    ]
    if min_days is not None:
        steps.append({"label": f"Minimum level ({min_days} days)",
                      "formula": f"MAX(CEIL({per_day:.2f} x {min_days}) = {math.ceil(per_day * min_days)}, avg per sale {per_sale})",
                      "value": _fmt(o.MinQty)})
    else:
        steps.append({"label": "Minimum level", "formula": "stored with the order", "value": _fmt(o.MinQty)})
    if max_days is not None:
        steps.append({"label": f"Maximum level ({max_days} days)",
                      "formula": f"MAX(CEIL({per_day:.2f} x {max_days}) = {math.ceil(per_day * max_days)}, biggest single sale)",
                      "value": _fmt(o.MaxQty)})
    else:
        steps.append({"label": "Maximum level", "formula": "stored with the order", "value": _fmt(o.MaxQty)})
    steps += [
        {"label": "Stock at order time", "formula": f"{_fmt(stock)} {'<' if stock < _num(o.MinQty) else '>='} minimum {_fmt(o.MinQty)}", "value": _fmt(stock)},
        {"label": "Need", "formula": f"maximum {_fmt(o.MaxQty)} - stock {_fmt(stock)}", "value": _fmt(_num(o.MaxQty) - stock)},
        {"label": "Packs", "formula": f"CEIL({_fmt(_num(o.MaxQty) - stock)} / pack {_fmt(pack)})", "value": _fmt(o.OrgOrderQty)},
    ]
    return steps


def _rulebook_steps(o, stats, params):
    sls, stock, pack = _num(o.SLSQty), _num(o.TotalStock), _num(o.SaleUnit)
    window = params["window_days"]
    per_day = sls / float(window)
    avg_bill = sls / stats["bills"] if stats["bills"] else 0
    terms = [
        (f"Cover {params['max_days']} days", per_day * params["max_days"], f"{per_day:.2f} x {params['max_days']}"),
        ("Biggest bill", stats["max_bill_qty"], f"bill total ({window} days)"),
        ("Biggest day", _num(o.MaxSaleQty) or stats["max_day_qty"], "one day's total"),
        ("Average bill", avg_bill, f"{_fmt(sls)} / {stats['bills']} bills"),
    ]
    gross = max(t[1] for t in terms)
    steps = [{"label": f"{window}-day sales", "formula": f"{_fmt(sls)} qty", "value": _fmt(sls)},
             {"label": "Average per day", "formula": f"{_fmt(sls)} / {window}", "value": f"{per_day:.2f}"}]
    steps += [{"label": label, "formula": text, "value": f"{value:.2f}".rstrip("0").rstrip("."),
               "winner": value == gross} for label, value, text in terms]
    steps += [
        {"label": "Target", "formula": "the biggest of the four above", "value": _fmt(_num(o.MaxQty))},
        {"label": "Need", "formula": f"target {_fmt(o.MaxQty)} - stock {_fmt(stock)}", "value": _fmt(_num(o.MaxQty) - stock)},
        {"label": "Packs", "formula": f"CEIL({_fmt(_num(o.MaxQty) - stock)} / pack {_fmt(pack)})", "value": _fmt(o.OrgOrderQty)},
    ]
    return steps


def product_reason(store_name, product_code):
    """None when the product is not in the store's current order."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        o = cur.execute(
            "SELECT TOP 1 ProductCode, ProductName, OrderId, WantedDate, TotalStock, SaleUnit, SLSQty, Frequence, "
            "MinQty, MaxQty, MaxSaleQty, Transactiondate, OrgOrderQty, OrderQty, WantedType, "
            "LastSaleDate, LastReceivedDate FROM OrderManagement WHERE StoreName = ? AND ProductCode = ? "
            "ORDER BY WantedDate DESC",
            store_name, product_code,
        ).fetchone()
        if not o:
            return None
        header = cur.execute(
            "SELECT TOP 1 MinDays, MaxDays FROM OrderHeaderDetails WHERE StoreName = ? AND OrderId = ? "
            "ORDER BY OrderDateTime DESC",
            store_name, o.OrderId,
        ).fetchone()
        end = o.WantedDate or datetime.datetime.now()
        start = datetime.datetime.combine(end.date() - datetime.timedelta(days=WINDOW_DAYS), datetime.time())
        stats = _sales(cur, store_name, int(_num(o.ProductCode)), start, end)

    wanted = (o.WantedType or "").strip()
    min_days = int(header.MinDays) if header and header.MinDays is not None else None
    max_days = int(header.MaxDays) if header and header.MaxDays is not None else None
    if wanted.startswith("Rule Book"):
        engine = "RULEBOOK"
        params = rulebook_order.rule_params(store_name)
        steps = _rulebook_steps(o, stats, params)
        reason = ("Rare mover: 1 pack for manual review." if "Rare" in wanted
                  else f"Stock {_fmt(o.TotalStock)} is below the target {_fmt(o.MaxQty)} "
                       f"(set by {wanted.split('·')[-1].strip().lower()}), so the gap is ordered.")
    else:
        engine = "LEGACY"
        steps = _legacy_steps(o, min_days, max_days)
        reason = _LEGACY_REASONS.get(wanted) or (
            f"Stock {_fmt(o.TotalStock)} is below the minimum {_fmt(o.MinQty)}, so it is ordered up to {_fmt(o.MaxQty)}.")
        if wanted in ("Rare Moment", "Additional Row"):
            steps = steps[:3] + [{"label": "Stock at order time", "formula": wanted, "value": _fmt(o.TotalStock)},
                                 {"label": "Packs", "formula": "fixed top-up", "value": _fmt(o.OrgOrderQty)}]
    changed = _num(o.OrderQty) != _num(o.OrgOrderQty)
    return {
        "product_code": int(_num(o.ProductCode)),
        "product_name": o.ProductName,
        "engine": engine,
        "wanted_type": wanted,
        "reason": reason,
        "order_id": o.OrderId,
        "order_time": _iso(o.WantedDate),
        "min_days": min_days,
        "max_days": max_days,
        "stock": _num(o.TotalStock),
        "pack": _num(o.SaleUnit),
        "sales_90d": _num(o.SLSQty),
        "sale_count": _num(o.Frequence),
        "min_qty": _num(o.MinQty),
        "max_qty": _num(o.MaxQty),
        "calculated_qty": _num(o.OrgOrderQty),
        "final_qty": _num(o.OrderQty),
        "changed_by_operator": changed,
        "last_sale": _iso(o.LastSaleDate),
        "last_received": _iso(o.LastReceivedDate),
        "steps": steps,
        "window": {"from": _iso(start), "to": _iso(end), "days": WINDOW_DAYS},
        "sales": stats,
    }
