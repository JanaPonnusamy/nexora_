"""Supplier Rate Engine -- cross-tenant purchase-cost loss computation.

Two baselines, same shape of result:

  4_supplier     SMS/Nathan actual cost vs the lowest of the 4 external
                 supplier rates (from the harvested rate workbook -- see
                 lowest_rate_list below).
  nathan_actual  SMS actual cost vs Nathan's own actual cost for the same
                 product (name-matched), using the MEDIAN Nathan cost per
                 product/month as the benchmark (a single bad data-entry
                 row must not inflate the whole product's loss -- see
                 memory nmw-purchase-entry-matching / the one-off analysis
                 that first hit this). Cost-ratio outliers beyond 5x / below
                 0.2x between the two sides are dropped as pack-size
                 mismatches, not real pricing signal, not as a loss.

Only reads. Nothing here writes to either tenant's database.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime

from modules.supplier_rate_engine import repository as repo

OUTLIER_RATIO_HIGH = 5.0
OUTLIER_RATIO_LOW = 0.2


def _unit_cost(row):
    qty = float(row.get("qty") or 0) + float(row.get("free_qty") or 0)
    cost = row.get("item_cost") or row.get("purchase_price") or 0
    return float(cost or 0), qty


def _ym(d):
    if isinstance(d, (datetime, date)):
        return f"{d.year:04d}-{d.month:02d}"
    return str(d)[:7]


def _year_bounds(year):
    return date(year, 1, 1), date(year + 1, 1, 1)


# --------------------------------------------------------------------------
# Baseline: 4-supplier lowest rate (reads the harvested rate workbook)
# --------------------------------------------------------------------------

def lowest_rate_list(workbook_rows, window="45d", as_of=None):
    """workbook_rows: pre-parsed rows from the "Supplier-wise" sheet(s) of the
    harvested 4-supplier rate workbook(s) -- [{product_code, product_name,
    pack, supplier, rate, received_date, store, bill_no}, ...]. Keeps, per
    product, the lowest rate seen either in the last 45 days (window="45d")
    or on the single most recent bill (window="last_bill") as of `as_of`
    (default: today)."""
    as_of = as_of or date.today()
    by_product = defaultdict(list)
    for r in workbook_rows:
        rd = r.get("received_date")
        if isinstance(rd, datetime):
            rd = rd.date()
        if not isinstance(rd, date):
            continue
        by_product[str(r.get("product_name") or "").strip().upper()].append({**r, "received_date": rd})

    out = []
    for _, rows in by_product.items():
        rows.sort(key=lambda r: r["received_date"], reverse=True)
        if window == "last_bill":
            candidates = [rows[0]] if rows else []
        else:
            cutoff = as_of.fromordinal(as_of.toordinal() - 45)
            candidates = [r for r in rows if r["received_date"] >= cutoff] or rows[:1]
        if not candidates:
            continue
        best = min(candidates, key=lambda r: float(r.get("rate") or float("inf")))
        out.append({
            "product_code": best.get("product_code"),
            "product_name": best.get("product_name"),
            "pack": best.get("pack"),
            "cost": round(float(best.get("rate") or 0), 2),
            "rate_date": best["received_date"],
            "store": best.get("store"),
            "supplier": best.get("supplier"),
            "window": window,
        })
    return sorted(out, key=lambda r: str(r["product_name"] or ""))


# --------------------------------------------------------------------------
# Baseline: Nathan actual cost vs SMS actual cost, same product (by name)
# --------------------------------------------------------------------------

def _nathan_benchmarks(nathan_rows):
    """{(norm_name, ym): median_unit_cost} over Nathan's purchase lines."""
    buckets = defaultdict(list)
    for r in nathan_rows:
        cost, qty = _unit_cost(r)
        if cost <= 0 or qty <= 0:
            continue
        key = (repo.normalize_name(r.get("product_name")), _ym(r.get("grn_date")))
        buckets[key].append(cost)
    return {k: statistics.median(v) for k, v in buckets.items()}


def nathan_vs_sms_loss(period_start, period_end):
    sms_rows = repo.sms_purchase_lines(period_start, period_end)
    nathan_rows = repo.nathan_purchase_lines(period_start, period_end)
    benchmarks = _nathan_benchmarks(nathan_rows)

    bill_rows = []
    matched = 0
    for r in sms_rows:
        cost, qty = _unit_cost(r)
        if cost <= 0 or qty <= 0:
            continue
        key = (repo.normalize_name(r.get("product_name")), _ym(r.get("grn_date")))
        benchmark = benchmarks.get(key)
        if benchmark is None:
            continue
        matched += 1
        ratio = cost / benchmark if benchmark else None
        if ratio is not None and (ratio > OUTLIER_RATIO_HIGH or ratio < OUTLIER_RATIO_LOW):
            continue
        loss = round((cost - benchmark) * qty, 2)
        bill_rows.append({
            "bill_no": f"{r.get('invoice_series') or ''}{r.get('grn_number') or ''}".strip() or None,
            "grn_date": r.get("grn_date"),
            "store": r.get("store"),
            "product_code": r.get("product_code"),
            "product_name": r.get("product_name"),
            "qty": qty,
            "actual_cost": round(cost, 2),
            "benchmark_cost": round(benchmark, 2),
            "loss": loss,
        })

    return {
        "bill_rows": bill_rows,
        "match_rate": round(matched / len(sms_rows), 4) if sms_rows else 0.0,
        "sms_line_count": len(sms_rows),
        "matched_line_count": matched,
    }


# --------------------------------------------------------------------------
# Aggregation: monthwise/store-wise, top-N consolidated, YTD
# --------------------------------------------------------------------------

def aggregate_loss(bill_rows):
    by_month_store = defaultdict(lambda: {"qty": 0.0, "loss": 0.0})
    by_store_ytd = defaultdict(float)
    by_product = defaultdict(lambda: {"total_loss": 0.0, "by_store": defaultdict(float),
                                       "by_month": defaultdict(lambda: defaultdict(lambda: {"qty": 0.0, "loss": 0.0}))})

    for r in bill_rows:
        if r["loss"] <= 0:
            continue
        ym = _ym(r["grn_date"])
        store = r["store"]
        by_month_store[(ym, store)]["qty"] += r["qty"]
        by_month_store[(ym, store)]["loss"] += r["loss"]
        by_store_ytd[store] += r["loss"]

        key = repo.normalize_name(r["product_name"])
        p = by_product[key]
        p["name"] = r["product_name"]
        p["product_code"] = r.get("product_code")
        p["total_loss"] += r["loss"]
        p["by_store"][store] += r["loss"]
        p["by_month"][ym][store]["qty"] += r["qty"]
        p["by_month"][ym][store]["loss"] += r["loss"]

    monthwise = [{"ym": ym, "store": store, "qty": round(v["qty"], 2), "loss": round(v["loss"], 2)}
                 for (ym, store), v in sorted(by_month_store.items())]

    top_products = []
    for key, p in sorted(by_product.items(), key=lambda kv: -kv[1]["total_loss"])[:25]:
        month_rows = []
        for ym, stores in sorted(p["by_month"].items()):
            for store, v in sorted(stores.items()):
                month_rows.append({"ym": ym, "store": store, "qty": round(v["qty"], 2), "loss": round(v["loss"], 2)})
        top_products.append({
            "product_code": p["product_code"],
            "product_name": p["name"],
            "total_loss": round(p["total_loss"], 2),
            "by_store": {k: round(v, 2) for k, v in p["by_store"].items()},
            "by_month": month_rows,
        })

    return {
        "ytd_total_loss": round(sum(by_store_ytd.values()), 2),
        "ytd_by_store": {k: round(v, 2) for k, v in by_store_ytd.items()},
        "monthwise": monthwise,
        "top_products": top_products,
    }


# --------------------------------------------------------------------------
# Reusable engine v2: NMW variant picker + (name, MRP)-keyed comparison,
# unit-aware, single tenant per run (SMS or Success, never merged).
# --------------------------------------------------------------------------

def nmw_variant_picker(product_names, period_start, period_end):
    """For each name in `product_names` (as given in an uploaded reference
    file), find every distinct stored NMW variant (exact substring match,
    no fuzzy scoring) with its MRP/unit/sample cost, for the user to review
    and select before any comparison runs -- see the NAN PRO false-match
    incident: a bare family name like "OMEE" must never be silently
    resolved to one row."""
    results = []
    for name in product_names:
        variants = repo.nathan_variant_search(str(name).strip(), period_start, period_end)
        results.append({
            "query": name,
            "variants": [{
                "product_name": v["product_name"],
                "mrp": v["mrp"],
                "sale_unit": v["sale_unit"],
                "purchase_unit": v["purchase_unit"],
                "line_count": v["line_count"],
                "min_cost": round(float(v["min_cost"]), 2) if v["min_cost"] is not None else None,
                "max_cost": round(float(v["max_cost"]), 2) if v["max_cost"] is not None else None,
            } for v in variants],
        })
    return results


def _variant_key(name, mrp):
    return (repo.normalize_name(name), round(float(mrp), 2) if mrp is not None else None)


def nmw_benchmarks(selected_variants, period_start, period_end):
    """One fixed low-rate benchmark per (normalized name, MRP) variant,
    sourced only from NMW, across the whole period (not per-month -- a
    single achievable floor per variant, per this session's standing
    direction: 'compare all bills with this one price'). Outlier floor:
    drop a raw itemcost row if it's under 20% of that variant's own median
    (the NAN PRO / ₹0.01-promo-row bug) before taking MIN. Returns
    {variant_key: {...}} including which store/bill/date achieved it and
    the unit recorded there, so a unit mismatch against the compared tenant
    can be flagged rather than assumed away."""
    wanted = {_variant_key(v["product_name"], v["mrp"]) for v in selected_variants}
    rows = repo.nathan_purchase_lines(period_start, period_end, store=repo.NMW_STORE)

    buckets = defaultdict(list)
    for r in rows:
        key = _variant_key(r.get("product_name"), r.get("mrp"))
        if key not in wanted:
            continue
        cost, qty = _unit_cost(r)
        if cost <= 0 or qty <= 0:
            continue
        buckets[key].append(r)

    out = {}
    for key, variant_rows in buckets.items():
        costs = [_unit_cost(r)[0] for r in variant_rows]
        med = statistics.median(costs)
        floor = med * OUTLIER_RATIO_LOW
        believable = [r for r in variant_rows if _unit_cost(r)[0] >= floor] or variant_rows
        best = min(believable, key=lambda r: _unit_cost(r)[0])
        out[key] = {
            "rate": round(_unit_cost(best)[0], 2),
            "store": best.get("store"),
            "bill_no": best.get("grn_number"),
            "date": best.get("grn_date"),
            "supplier": best.get("supplier_name"),
            "mrp": best.get("mrp"),
            "sale_unit": best.get("sale_unit"),
            "purchase_unit": best.get("purchase_unit"),
        }
    return out


def _resolve_unit(row):
    """Bill-line SaleUnit is frequently NULL on SMS/Success -- that column
    is unreliable per-row metadata (confirmed this session), so prefer it
    when present but fall back to nothing rather than guessing."""
    return row.get("sale_unit") or row.get("purchase_unit")


def store_tenant_variance_report(tenant_key, selected_variants, period_start, period_end):
    """Single-tenant (SMS or Success -- never both) comparison of every real
    purchase line/batch for the selected NMW variants against that variant's
    one fixed NMW low rate. Success is grouped by BatchCode in addition to
    bill number (batch-wise, per this tenant's requirement); SMS stays
    bill-wise. MRP is part of the match key, so a line whose own MRP doesn't
    match any selected variant for that product name is left unmatched
    rather than compared against the wrong MRP's rate."""
    tenant_key = tenant_key.upper()
    conf = repo.STORE_TENANTS.get(tenant_key)
    if not conf:
        raise ValueError(f"Unknown tenant '{tenant_key}' (expected SMS or SUCCESS)")

    benchmarks = nmw_benchmarks(selected_variants, period_start, period_end)
    lines = repo.store_tenant_purchase_lines(tenant_key, period_start, period_end)

    bill_rows = []
    unmatched_mrp = 0
    for r in lines:
        key = _variant_key(r.get("product_name"), r.get("mrp"))
        bench = benchmarks.get(key)
        if bench is None:
            # Same normalized name but no selected variant has this MRP:
            # could be a genuinely different pack, not an MRP we were asked
            # to compare -- count it, don't guess a benchmark for it.
            if any(k[0] == repo.normalize_name(r.get("product_name")) for k in benchmarks):
                unmatched_mrp += 1
            continue
        cost, qty = _unit_cost(r)
        if cost <= 0 or qty <= 0:
            continue

        line_unit = _resolve_unit(r)
        bench_unit = bench.get("sale_unit") or bench.get("purchase_unit")
        unit_mismatch = bool(line_unit and bench_unit and str(line_unit) != str(bench_unit))
        unit_known = bool(line_unit and bench_unit)

        loss = round((cost - bench["rate"]) * qty, 2)
        bill_rows.append({
            "bill_no": f"{r.get('invoice_series') or ''}{r.get('grn_number') or ''}".strip() or None,
            "batch_code": r.get("batch_code"),
            "grn_date": r.get("grn_date"),
            "store": r.get("store"),
            "product_code": r.get("product_code"),
            "product_name": r.get("product_name"),
            "mrp": r.get("mrp"),
            "qty": qty,
            "actual_cost": round(cost, 2),
            "nmw_low_rate": bench["rate"],
            "nmw_rate_source": f"{bench.get('store')} / bill {bench.get('bill_no')} ({bench.get('date')})",
            "unit": line_unit,
            "unit_known": unit_known,
            "unit_mismatch": unit_mismatch,
            "loss": loss,
        })

    group_field = "batch_code" if conf["batch_wise"] else "bill_no"
    agg = aggregate_loss(bill_rows)
    return {
        "tenant": tenant_key,
        "batch_wise": conf["batch_wise"],
        "group_field": group_field,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "bill_rows": bill_rows,
        "unmatched_mrp_lines": unmatched_mrp,
        "unit_mismatch_count": sum(1 for r in bill_rows if r["unit_mismatch"]),
        "unit_unknown_count": sum(1 for r in bill_rows if not r["unit_known"]),
        **agg,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def tenant_loss_report(tenant, baseline, year):
    """Full report for one tenant/baseline/year -- the shape the router
    serialises to JSON or Excel."""
    start, end = _year_bounds(year)
    if baseline == "nathan_actual":
        result = nathan_vs_sms_loss(start, end)
        bill_rows = result["bill_rows"]
    else:
        raise ValueError(f"Unsupported baseline: {baseline}")

    agg = aggregate_loss(bill_rows)
    return {
        "tenant": tenant,
        "baseline": baseline,
        "period_start": start.isoformat(),
        "period_end": min(end, date.today()).isoformat(),
        "bill_rows": bill_rows,
        **agg,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
