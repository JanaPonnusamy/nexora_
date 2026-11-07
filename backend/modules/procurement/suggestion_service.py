"""Product Suggestion panel: best / frequent supplier and other stores'
non-moving stock for ONE store product (any product -- not tied to a refresh).

Supplier ranking is the Purchase Manager's own recommendation blend
(frontend purchaseValue.ts rankSuppliersForRecommendation + AA_WEIGHTS):
last purchase recency 40, purchase frequency 30, cheapest PTR 20, live stock
10 -- so "best" means the same thing in the web and desktop apps.
  best      -- top of that ranking;
  frequent  -- most purchases;
  latest    -- most recent purchase.

Other stores: the product's mapped code at every other active store of the
tenant (dbo.product_mapping, AUTO/APPROVED, both directions -- ProductCode is
never a cross-store key on its own), with stock and movement. NON-MOVING =
stock > 0 and no sale in the window (same 90-day window and zero-sales rule
as the engine's NONMOVING movement class) -- stock that could be moved here
instead of buying.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException

from modules.procurement import intelligence_repository as intel_repo
from modules.procurement import suggestion_repository as repo

WEIGHTS = {"last_purchase": 40, "frequency": 30, "ptr": 20, "live_stock": 10}
WINDOW_DAYS = 90
TREND_MONTHS = 4
SUPPLIER_LIMIT = 8


def _num(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).timestamp()
    try:
        return datetime.fromisoformat(str(value)[:19]).timestamp()
    except ValueError:
        return None


def rank_suppliers(suppliers):
    """Score and order supplier rows (pure). Each row needs purchase_frequency,
    last_grn_date, last_purchase_rate (PTR) and live_stock (number or None)."""
    if not suppliers:
        return []
    max_freq = max([_num(s.get("purchase_frequency")) or 0 for s in suppliers] + [1])
    times = [t for t in (_ts(s.get("last_grn_date")) for s in suppliers) if t is not None]
    newest, oldest = (max(times), min(times)) if times else (None, None)
    rates = [r for r in (_num(s.get("ptr")) for s in suppliers) if r is not None and r > 0]
    lo, hi = (min(rates), max(rates)) if rates else (None, None)

    def score(s):
        sc = 0.0
        t = _ts(s.get("last_grn_date"))
        if t is not None and newest is not None:
            span = newest - oldest
            sc += WEIGHTS["last_purchase"] * ((t - oldest) / span if span > 0 else 1)
        sc += WEIGHTS["frequency"] * ((_num(s.get("purchase_frequency")) or 0) / max_freq)
        r = _num(s.get("ptr"))
        if r is not None and r > 0 and lo is not None:
            span = hi - lo
            sc += WEIGHTS["ptr"] * ((hi - r) / span if span > 0 else 1)
        if (_num(s.get("live_stock")) or 0) > 0:
            sc += WEIGHTS["live_stock"]
        return sc

    ranked = sorted(suppliers, key=score, reverse=True)
    for s in ranked:
        s["score"] = round(score(s), 1)
    best = ranked[0]["supplier_code"]
    by_freq = max(ranked, key=lambda s: _num(s.get("purchase_frequency")) or 0)
    frequent = by_freq["supplier_code"] if (_num(by_freq.get("purchase_frequency")) or 0) > 0 else None
    dated = [s for s in ranked if _ts(s.get("last_grn_date")) is not None]
    latest = max(dated, key=lambda s: _ts(s["last_grn_date"]))["supplier_code"] if dated else None
    for s in ranked:
        tags = []
        if s["supplier_code"] == best:
            tags.append("best")
        if s["supplier_code"] == frequent:
            tags.append("frequent")
        if s["supplier_code"] == latest:
            tags.append("latest")
        if (_num(s.get("live_stock")) or 0) > 0:
            tags.append("live")
        if s.get("is_warehouse"):
            tags.append("warehouse")
        s["tags"] = tags
    return ranked


def _merge_suppliers(purchases, live_rows):
    by_code = {}
    for p in purchases:
        row = dict(p)
        row["ptr"] = p.get("last_purchase_rate")
        row["live_stock"] = None
        by_code[p["supplier_code"]] = row
    for lv in live_rows:
        code = lv["supplier_code"]
        row = by_code.get(code)
        if row is None:
            row = {
                "supplier_code": code, "supplier_name": lv.get("supplier_name"),
                "purchase_frequency": 0, "last_grn_date": None, "last_grn_no": None,
                "last_purchase_rate": None, "last_item_cost": None, "last_mrp": None,
                "last_qty": None, "last_free": None, "last_discount": None,
                "ptr": lv.get("ptr"), "live_stock": None,
            }
            by_code[code] = row
        # ST_* is the warehouse's own stock bridged into the supplier-stock
        # list (stock-transfer series), not an outside supplier.
        if str(code).upper().startswith("ST_"):
            row["is_warehouse"] = True
            row["supplier_name"] = row.get("supplier_name") or f"Warehouse transfer ({code})"
        row["live_stock"] = (_num(row.get("live_stock")) or 0) + (_num(lv.get("available_stock")) or 0)
        row["live_ptr"] = lv.get("ptr")
        row["live_mrp"] = lv.get("mrp")
        row["live_scheme"] = lv.get("scheme") or (f"{lv['free']} free" if _num(lv.get("free")) else None)
        row["live_discount"] = lv.get("discount")
        if row.get("ptr") is None:
            row["ptr"] = lv.get("ptr")
    return list(by_code.values())


def _days_since(value):
    t = _ts(value)
    if t is None:
        return None
    return max(0, int((datetime.now().timestamp() - t) // 86400))


def other_stores(tenant_id, store_id, product_code):
    stores = [s for s in intel_repo.list_active_stores(tenant_id) if str(s["store_id"]).upper() != str(store_id).upper()]
    if not stores:
        return []
    mapped = intel_repo.resolve_mapped_stores(tenant_id, store_id, product_code, [s["store_id"] for s in stores])
    if not mapped:
        return []
    meta = {str(s["store_id"]).upper(): s for s in stores}
    facts = repo.store_product_facts(tenant_id, [(sid, m["product_code"]) for sid, m in mapped.items()], WINDOW_DAYS)
    out = []
    for f in facts:
        s = meta.get(str(f["store_id"]).upper(), {})
        stock = _num(f.get("stock")) or 0
        sold = _num(f.get("window_sales_qty")) or 0
        out.append({
            "store_id": f["store_id"],
            "store_code": s.get("store_code"),
            "store_name": s.get("store_name"),
            "product_code": f["product_code"],
            "product_name": f.get("product_name"),
            "stock": stock,
            "window_sales_qty": sold,
            "last_sale_date": f.get("last_sale_date"),
            "days_since_sale": _days_since(f.get("last_sale_date")),
            "last_purchase_date": f.get("last_purchase_date"),
            "non_moving": stock > 0 and sold <= 0,
        })
    # Non-moving stock first (biggest first), then the rest by stock.
    out.sort(key=lambda r: (not r["non_moving"], -r["stock"]))
    return out


def product_suggestions(tenant_id, store_id, product_code):
    if not store_id or product_code is None or not str(product_code).strip():
        raise HTTPException(status_code=400, detail="store_id and product_code are required")
    code = str(product_code).strip()
    suppliers = rank_suppliers(_merge_suppliers(
        repo.purchase_suppliers(tenant_id, store_id, code),
        repo.live_supplier_stock(tenant_id, store_id, code),
    ))[:SUPPLIER_LIMIT]
    stores = other_stores(tenant_id, store_id, code)
    return {
        "store_id": store_id,
        "product_code": code,
        "window_days": WINDOW_DAYS,
        "suppliers": suppliers,
        "other_stores": stores,
        "non_moving_stock": sum(r["stock"] for r in stores if r["non_moving"]),
    }


def _last_months(count):
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def store_trends(tenant_id, store_id, product_code):
    """Every active store's latest TREND_MONTHS months of movement for this
    product -- this store first, then each other store's mapped code (same
    product_mapping resolution as other_stores). A store with no mapping is
    left out; a mapped store with no ProductTrans rows has empty months.
    The window is one shared range for every store: it ends at the current
    month when any store has a row for it, else at the previous month (the
    current month's rollup may not have synced yet)."""
    if not store_id or product_code is None or not str(product_code).strip():
        raise HTTPException(status_code=400, detail="store_id and product_code are required")
    code = str(product_code).strip()
    stores = intel_repo.list_active_stores(tenant_id)
    meta = {str(s["store_id"]).upper(): s for s in stores}
    others = [s["store_id"] for s in stores if str(s["store_id"]).upper() != str(store_id).upper()]
    mapped = intel_repo.resolve_mapped_stores(tenant_id, store_id, code, others) if others else {}
    pairs = [(store_id, code)] + [(sid, m["product_code"]) for sid, m in mapped.items()]
    span = _last_months(TREND_MONTHS + 1)
    rows = repo.store_monthly_movement(tenant_id, pairs, TREND_MONTHS + 1)
    months = span[1:] if any(r["ym"] == span[-1] for r in rows) else span[:-1]
    by_store = {}
    for r in rows:
        by_store.setdefault(str(r["store_id"]).upper(), {})[r["ym"]] = r
    out = []
    for sid, pcode in pairs:
        key = str(sid).upper()
        s = meta.get(key, {})
        got = by_store.get(key, {})
        out.append({
            "store_id": sid,
            "store_code": s.get("store_code"),
            "store_name": s.get("store_name"),
            "product_code": str(pcode),
            "product_name": (mapped.get(sid) or {}).get("product_name"),
            "current": key == str(store_id).upper(),
            "months": [{
                "ym": ym,
                "in": _num(got[ym]["qty_in"]) if ym in got else None,
                "out": _num(got[ym]["qty_out"]) if ym in got else None,
                "stock": _num(got[ym]["stock"]) if ym in got else None,
            } for ym in months],
        })
    out[1:] = sorted(out[1:], key=lambda r: r["store_code"] or "")
    return {"product_code": code, "months": months, "stores": out}
