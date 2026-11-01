"""Non-Moving Stock Analysis -- classification, cross-store comparison,
transfer recommendations and the management summary.

Read-only and informational: it never writes stock, never creates a transfer
and never touches the Procurement decision engine / VPL / order generation.

Business rules (verified against live data and the legacy code, see
repository.py for the sources):

* Age = days since the LAST VALID SALE. Last purchase is never a substitute.
  Source order: PSI valid sale line -> ProductTrans.LastBillDate (POS rollup,
  covers sales before synced PSI history began) -> Batches.LastSaleDate. The
  source used is returned with every row, and a PSI / rollup disagreement is
  flagged rather than silently resolved (PSI, which honours
  TransactionValidity, wins).
* Classification bands (configurable, defaults 30/60/90/180/365 days):
  Active, Slow Moving, Very Slow, Non-Moving Risk, Non-Moving, Critical Dead
  Stock. A product with no sale in any source is NEW (first received within
  `new_days`, default 90 -- never dead stock) or NO SALES HISTORY.
* Only products with stock > 0 (authoritative store stock) are analysed and
  valued; a product whose batches still hold stock while the store stock is 0
  is flagged STOCK_MISMATCH, never valued.
* Valuation basis = cost (POS batch GrsStkValueatCost). PTR and MRP values are
  separate measures, never mixed into it.
* "Non-moving" (KPIs, Other Stores, transfer sources) = Non-Moving Risk or
  worse (> 90 days by default) plus No Sales History.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime

from fastapi import HTTPException

from modules.nonmoving_analysis import repository as repo
from modules.procurement import intelligence_repository as intel_repo

logger = logging.getLogger("nonmoving_analysis")

CLASSES = [
    ("ACTIVE", "Active"),
    ("SLOW", "Slow Moving"),
    ("VERY_SLOW", "Very Slow"),
    ("NM_RISK", "Non-Moving Risk"),
    ("NON_MOVING", "Non-Moving"),
    ("DEAD", "Critical Dead Stock"),
    ("NEW", "New - No Sale Yet"),
    ("NO_SALES", "No Sales History"),
]
CLASS_LABEL = dict(CLASSES)
BAND_CLASSES = ["ACTIVE", "SLOW", "VERY_SLOW", "NM_RISK", "NON_MOVING"]  # last band -> DEAD
NON_MOVING = {"NM_RISK", "NON_MOVING", "DEAD", "NO_SALES"}
DEFAULT_BANDS = (30, 60, 90, 180, 365)
NEAR_EXPIRY_DAYS = 90       # fixed in the store snapshot (batches expiring within 90 days)
CACHE_SECONDS = 30 * 60
MAX_PAGE = 1000


@dataclass(frozen=True)
class Config:
    bands: tuple = DEFAULT_BANDS
    new_days: int = 90            # no sale yet + first received within this = NEW
    recent_grn_days: int = 10     # legacy NM gate: a GRN this recent is flagged
    dest_cover_days: int = 30     # transfer: destination stock target = this many days of its sales
    source_keep_days: int = 90    # transfer: a still-selling source keeps this many days of its own sales
    dest_active_days: int = 30    # transfer: destination must have sold within this many days
    dest_min_bills: int = 2       # transfer: ... on at least this many bills in 90 days (not a one-off)


def parse_config(bands=None, new_days=None, dest_cover_days=None, source_keep_days=None):
    b = DEFAULT_BANDS
    if bands:
        try:
            vals = tuple(int(x) for x in str(bands).split(",") if str(x).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="bands must be 5 comma-separated day counts")
        if len(vals) != 5 or any(v <= 0 for v in vals) or list(vals) != sorted(set(vals)):
            raise HTTPException(status_code=400, detail="bands must be 5 increasing day counts, e.g. 30,60,90,180,365")
        b = vals
    kw = {"bands": b}
    if new_days:
        kw["new_days"] = int(new_days)
    if dest_cover_days:
        kw["dest_cover_days"] = int(dest_cover_days)
    if source_keep_days:
        kw["source_keep_days"] = int(source_keep_days)
    return Config(**kw)


def config_info(cfg: Config):
    b = cfg.bands
    ranges = [f"0-{b[0]}"] + [f"{b[i - 1] + 1}-{b[i]}" for i in range(1, 5)] + [f"> {b[4]}"]
    return {
        "bands": list(b),
        "classes": [{"key": k, "label": CLASS_LABEL[k], "days": r}
                    for k, r in zip(BAND_CLASSES + ["DEAD"], ranges)]
                   + [{"key": "NEW", "label": CLASS_LABEL["NEW"], "days": f"no sale, first received <= {cfg.new_days} days"},
                      {"key": "NO_SALES", "label": CLASS_LABEL["NO_SALES"], "days": "no sale in any source"}],
        "non_moving": sorted(NON_MOVING),
        "near_expiry_days": NEAR_EXPIRY_DAYS,
        "new_days": cfg.new_days,
        "transfer": {"dest_cover_days": cfg.dest_cover_days, "source_keep_days": cfg.source_keep_days,
                     "dest_active_days": cfg.dest_active_days, "dest_min_bills": cfg.dest_min_bills},
        "valuation": "Cost = POS batch stock value at cost (GrsStkValueatCost). PTR and MRP values are separate.",
    }


# --------------------------------------------------------------------------
# Pure row analysis
# --------------------------------------------------------------------------

def _d(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _n(value):
    try:
        return 0.0 if value is None else float(value)
    except (TypeError, ValueError):
        return 0.0


def classify_days(days, bands):
    for key, limit in zip(BAND_CLASSES, bands):
        if days <= limit:
            return key
    return "DEAD"


def resolve_last_sale(raw):
    """(date, source, conflict) -- PSI first, then rollup, then batch."""
    psi, rollup, batch = _d(raw.get("last_sale_psi")), _d(raw.get("last_sale_rollup")), _d(raw.get("last_sale_batch"))
    conflict = bool(psi and rollup and psi != rollup)
    if psi:
        return psi, "PSI", conflict
    if rollup:
        return rollup, "ROLLUP", False
    if batch:
        return batch, "BATCH", False
    return None, None, False


def analyse(raw, cfg: Config, today: date):
    """One snapshot row -> the analysed row (classification, value, flags)."""
    stock = _n(raw.get("stock"))
    batch_stock = _n(raw.get("batch_stock"))
    last_sale, source, conflict = resolve_last_sale(raw)
    days = (today - last_sale).days if last_sale else None
    intro = _d(raw.get("first_receipt_date")) or _d(raw.get("created_date"))
    if last_sale is not None:
        cls = classify_days(max(0, days), cfg.bands)
    elif intro and (today - intro).days <= cfg.new_days:
        cls = "NEW"
    else:
        cls = "NO_SALES"
    in_stock = stock > 0
    flags = []
    if abs(stock - batch_stock) > 0.001:
        flags.append("STOCK_MISMATCH")
    if conflict:
        flags.append("SALE_DATE_CONFLICT")
    if source in ("ROLLUP", "BATCH"):
        flags.append(f"LAST_SALE_FROM_{source}")
    last_grn = _d(raw.get("last_grn_date"))
    if last_grn and (today - last_grn).days <= cfg.recent_grn_days:
        flags.append("RECENT_GRN")
    if int(_n(raw.get("invalid_lines_180"))) > 0:
        flags.append("INVALID_SALES")
    if not raw.get("is_active"):
        flags.append("INACTIVE")
    if last_sale is None and intro is None and not raw.get("last_purchase_date"):
        flags.append("NO_TXN_HISTORY")
    expired_qty = _n(raw.get("expired_qty"))
    near_qty = _n(raw.get("near_expiry_qty"))
    if int(_n(raw.get("batch_count"))) == 0:
        expiry = "No batch"
    elif expired_qty > 0:
        expiry = "Expired"
    elif near_qty > 0:
        expiry = "Near expiry"
    elif int(_n(raw.get("no_expiry_batches"))) > 0:
        expiry = "No date"
    else:
        expiry = "OK"
    value = lambda k: round(_n(raw.get(k)), 2) if in_stock else 0.0
    sale_unit = _n(raw.get("sale_unit")) or 1.0
    return {
        "product_code": str(raw.get("product_code")),
        "product_name": raw.get("product_name"),
        "unit": raw.get("unit"),
        "pack": raw.get("pack"),
        "sale_unit": sale_unit,
        "product_type": "Non Pharma" if raw.get("product_type") == 0 else "Pharma",
        "is_active": bool(raw.get("is_active")),
        "stock": stock,
        "stock_packs": round(stock / sale_unit, 2),
        "batch_stock": batch_stock,
        "batch_count": int(_n(raw.get("batch_count"))),
        "cost_value": value("cost_value"),
        "ptr_value": value("ptr_value"),
        "mrp_value": value("mrp_value"),
        "expired_qty": expired_qty if in_stock else 0.0,
        "expired_value": value("expired_value"),
        "near_expiry_qty": near_qty if in_stock else 0.0,
        "near_expiry_value": value("near_expiry_value"),
        "earliest_expiry": _d(raw.get("earliest_expiry")),
        "expiry_status": expiry,
        "last_sale_date": last_sale,
        "last_sale_source": source,
        "last_sale_psi": _d(raw.get("last_sale_psi")),
        "last_sale_rollup": _d(raw.get("last_sale_rollup")),
        "days_since_sale": days,
        "last_purchase_date": _d(raw.get("last_purchase_date")),
        "last_grn_date": last_grn,
        "first_receipt_date": intro,
        "sales_30": _n(raw.get("sales_30")),
        "sales_90": _n(raw.get("sales_90")),
        "sales_180": _n(raw.get("sales_180")),
        "bills_90": int(_n(raw.get("bills_90"))),
        "invalid_lines_180": int(_n(raw.get("invalid_lines_180"))),
        "supplier_code": raw.get("supplier_code"),
        "supplier_name": raw.get("supplier_name") or raw.get("supplier_code"),
        "classification": cls,
        "classification_label": CLASS_LABEL[cls],
        "non_moving": in_stock and cls in NON_MOVING,
        "in_stock": in_stock,
        "flags": flags,
    }


# --------------------------------------------------------------------------
# Snapshot cache (one bulk query per store, kept for CACHE_SECONDS)
# --------------------------------------------------------------------------

_cache: dict = {}             # (TENANT, STORE) -> {"at": epoch, "rows": [...]}
_edges: dict = {}             # TENANT -> {"at": epoch, "adj": {...}}
_locks: dict = {}
_guard = threading.Lock()


def _lock(key):
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def _is_warehouse(store):
    try:
        from modules.legacy_order.service import is_warehouse_store
        return is_warehouse_store(store.get("store_code"))
    except Exception:  # pragma: no cover - legacy module optional
        return str(store.get("store_code") or "").upper() == "NMW"


def tenant_stores(tenant_id):
    stores = intel_repo.list_active_stores(tenant_id)
    for s in stores:
        s["is_warehouse"] = _is_warehouse(s)
    return stores


def _store_of(tenant_id, store_id):
    for s in tenant_stores(tenant_id):
        if str(s["store_id"]).upper() == str(store_id or "").upper():
            return s
    raise HTTPException(status_code=404, detail="Store not found in this tenant")


def _snapshot(tenant_id, store, refresh=False):
    key = (str(tenant_id).upper(), str(store["store_id"]).upper())
    hit = _cache.get(key)
    if hit and not refresh and time.time() - hit["at"] < CACHE_SECONDS:
        return hit
    with _lock(key):
        hit = _cache.get(key)
        if hit and not refresh and time.time() - hit["at"] < CACHE_SECONDS:
            return hit
        t0 = time.time()
        rows = repo.store_snapshot(tenant_id, store["store_id"], store.get("is_warehouse"), NEAR_EXPIRY_DAYS)
        hit = {"at": time.time(), "rows": rows, "seconds": round(time.time() - t0, 2)}
        _cache[key] = hit
        logger.info("non-moving snapshot %s: %d rows in %.1fs", store.get("store_code"), len(rows), hit["seconds"])
        return hit


def _all_snapshots(tenant_id, stores, refresh=False):
    # Two stores at a time: a cold build reads every sale line of the tenant
    # and shares the live SQL Server with everyone else.
    with ThreadPoolExecutor(max_workers=2) as pool:
        hits = list(pool.map(lambda s: _snapshot(tenant_id, s, refresh), stores))
    return {str(s["store_id"]).upper(): h for s, h in zip(stores, hits)}


def _adjacency(tenant_id, stores, snaps, refresh=False):
    """{(STORE, code): {OTHER_STORE: {code: confidence}}} over direct mapping
    edges among products present in the snapshots."""
    key = str(tenant_id).upper()
    hit = _edges.get(key)
    oldest = min(h["at"] for h in snaps.values()) if snaps else 0
    if hit and not refresh and time.time() - hit["at"] < CACHE_SECONDS and hit["at"] >= oldest - 1:
        return hit["adj"]
    with _lock(("edges", key)):
        keep = {(sid, str(r["product_code"])) for sid, h in snaps.items() for r in h["rows"]}
        adj = {}
        for sa, ca, sb, cb, conf in repo.mapping_edges(tenant_id, [s["store_id"] for s in stores], keep):
            adj.setdefault((sa, ca), {}).setdefault(sb, {})[cb] = conf
            adj.setdefault((sb, cb), {}).setdefault(sa, {})[ca] = conf
        _edges[key] = {"at": time.time(), "adj": adj}
        return adj


def _analysed(tenant_id, store, cfg, refresh=False):
    hit = _snapshot(tenant_id, store, refresh)
    today = date.fromtimestamp(hit["at"])
    return [analyse(r, cfg, today) for r in hit["rows"]], hit


@dataclass
class Network:
    stores: list
    meta: dict
    rows: dict                    # STORE -> {code: analysed row}
    adj: dict
    refreshed_at: float = 0.0
    timings: dict = field(default_factory=dict)

    def peers(self, store_id, code):
        """{OTHER_STORE: (code, confidence, ambiguous)} for one product."""
        out = {}
        for sid, codes in (self.adj.get((store_id, str(code))) or {}).items():
            present = {c: conf for c, conf in codes.items() if c in self.rows.get(sid, {})}
            if not present:
                continue
            best = max(present, key=lambda c: (present[c] or 0, self.rows[sid][c]["stock"]))
            out[sid] = (best, present[best], len(present) > 1)
        return out


_networks: dict = {}          # (TENANT, Config) -> (snapshot stamps, Network)


def network(tenant_id, cfg, refresh=False):
    stores = tenant_stores(tenant_id)
    snaps = _all_snapshots(tenant_id, stores, refresh)
    stamps = tuple(sorted((sid, h["at"]) for sid, h in snaps.items()))
    key = (str(tenant_id).upper(), cfg)
    cached = _networks.get(key)
    if cached and cached[0] == stamps and not refresh:
        return cached[1]
    # One build at a time per tenant (the warm-up thread and a request can
    # arrive together); the second caller then takes the first one's result.
    with _lock(("network", key[0])):
        cached = _networks.get(key)
        if cached and cached[0] == stamps:
            return cached[1]
        return _build_network(tenant_id, cfg, stores, snaps, stamps, key, refresh)


def _build_network(tenant_id, cfg, stores, snaps, stamps, key, refresh):
    adj = _adjacency(tenant_id, stores, snaps, refresh)
    rows = {}
    for sid, hit in snaps.items():
        today = date.fromtimestamp(hit["at"])
        rows[sid] = {str(r["product_code"]): analyse(r, cfg, today) for r in hit["rows"]}
    net = Network(
        stores=stores,
        meta={str(s["store_id"]).upper(): s for s in stores},
        rows=rows,
        adj=adj,
        refreshed_at=min(h["at"] for h in snaps.values()) if snaps else time.time(),
        timings={sid: h.get("seconds") for sid, h in snaps.items()},
    )
    for k in [k for k in _networks if k[0] == key[0]]:
        _networks.pop(k, None)          # one config per tenant is plenty
    _networks[key] = (stamps, net)
    return net


def _stamp(epoch):
    return datetime.fromtimestamp(epoch).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Filtering / paging helpers
# --------------------------------------------------------------------------

_SORTABLE = {
    "product_code", "product_name", "unit", "pack", "stock", "cost_value", "ptr_value", "mrp_value",
    "last_sale_date", "days_since_sale", "last_purchase_date", "last_grn_date", "supplier_name",
    "expiry_status", "classification", "sales_30", "sales_90", "earliest_expiry", "near_expiry_value",
    "expired_value", "other_sales_30", "other_stock", "active_stores", "suggested_qty", "transfer_value",
    "dest_need", "source_days_since_sale", "store_code",
}
_CLASS_ORDER = {k: i for i, (k, _) in enumerate(CLASSES)}


def _sort_key(field_name):
    def key(r):
        v = r.get(field_name)
        if field_name == "classification":
            v = _CLASS_ORDER.get(v, 99)
        if field_name == "days_since_sale" and v is None:
            v = 10 ** 6       # never sold sorts as the oldest
        if v is None:
            return (1, 0)
        if isinstance(v, (date, datetime)):
            return (0, v.toordinal())
        if isinstance(v, str):
            return (0, v.lower())
        return (0, v)
    return key


def _page(rows, sort, direction, page, page_size):
    sort = sort if sort in _SORTABLE else None
    if sort:
        rows = sorted(rows, key=_sort_key(sort), reverse=(direction or "desc").lower() == "desc")
        # Keep "no value" rows last either way.
        rows = [r for r in rows if r.get(sort) is not None or sort == "days_since_sale"] + \
               [r for r in rows if r.get(sort) is None and sort != "days_since_sale"]
    if page_size is None:               # export: every row, one "page"
        return rows, len(rows), 1, len(rows)
    size = max(1, min(int(page_size), MAX_PAGE))
    page = max(1, int(page or 1))
    return rows[(page - 1) * size: page * size], len(rows), page, size


def _text_match(row, q):
    return q in str(row.get("product_name") or "").lower() or q == str(row.get("product_code") or "").lower() \
        or q in str(row.get("supplier_name") or "").lower()


def filter_rows(rows, search=None, classes=None, ptype=None, supplier=None, min_days=None,
                max_days=None, expiry=None, include_zero=False, non_moving_only=False):
    q = (search or "").strip().lower()
    cls = {c.strip().upper() for c in str(classes or "").split(",") if c.strip()}
    out = []
    for r in rows:
        if not include_zero and not r["in_stock"]:
            continue
        if non_moving_only and not r["non_moving"]:
            continue
        if cls and r["classification"] not in cls:
            continue
        if ptype and r["product_type"].replace(" ", "").lower() != str(ptype).replace(" ", "").lower():
            continue
        if supplier and str(r.get("supplier_code") or "") != str(supplier):
            continue
        d = r["days_since_sale"]
        if min_days is not None and (d is not None and d < int(min_days)):
            continue
        if max_days is not None and (d is None or d > int(max_days)):
            continue
        if expiry:
            e = str(expiry).lower()
            if e == "expired" and r["expiry_status"] != "Expired":
                continue
            if e == "near" and r["expiry_status"] != "Near expiry":
                continue
            if e == "risk" and r["expiry_status"] not in ("Expired", "Near expiry"):
                continue
        if q and not _text_match(r, q):
            continue
        out.append(r)
    return out


def class_summary(rows):
    """Count / qty / cost / MRP value per classification over in-stock rows."""
    by = {k: {"key": k, "label": lbl, "products": 0, "qty": 0.0, "cost_value": 0.0, "mrp_value": 0.0}
          for k, lbl in CLASSES}
    for r in rows:
        if not r["in_stock"]:
            continue
        b = by[r["classification"]]
        b["products"] += 1
        b["qty"] += r["stock"]
        b["cost_value"] += r["cost_value"]
        b["mrp_value"] += r["mrp_value"]
    for b in by.values():
        b["qty"] = round(b["qty"], 2)
        b["cost_value"] = round(b["cost_value"], 2)
        b["mrp_value"] = round(b["mrp_value"], 2)
    return list(by.values())


def store_kpis(rows):
    stocked = [r for r in rows if r["in_stock"]]
    nm = [r for r in stocked if r["non_moving"]]
    dead = [r for r in stocked if r["classification"] == "DEAD"]
    return {
        "products_analyzed": len(stocked),
        "non_moving_products": len(nm),
        "non_moving_qty": round(sum(r["stock"] for r in nm), 2),
        "non_moving_value": round(sum(r["cost_value"] for r in nm), 2),
        "non_moving_mrp_value": round(sum(r["mrp_value"] for r in nm), 2),
        "dead_products": len(dead),
        "dead_value": round(sum(r["cost_value"] for r in dead), 2),
        "stock_value": round(sum(r["cost_value"] for r in stocked), 2),
        "stock_ptr_value": round(sum(r["ptr_value"] for r in stocked), 2),
        "stock_mrp_value": round(sum(r["mrp_value"] for r in stocked), 2),
        "expired_qty": round(sum(r["expired_qty"] for r in stocked), 2),
        "expired_value": round(sum(r["expired_value"] for r in stocked), 2),
        "near_expiry_value": round(sum(r["near_expiry_value"] for r in stocked), 2),
        "expiry_risk_value": round(sum(r["expired_value"] + r["near_expiry_value"] for r in stocked), 2),
        "stock_mismatch_products": sum(1 for r in stocked if "STOCK_MISMATCH" in r["flags"]),
        "no_sales_products": sum(1 for r in stocked if r["classification"] == "NO_SALES"),
        "new_products": sum(1 for r in stocked if r["classification"] == "NEW"),
    }


def _suppliers(rows):
    agg = {}
    for r in rows:
        if not r["in_stock"] or not r.get("supplier_code"):
            continue
        a = agg.setdefault(r["supplier_code"], {"code": r["supplier_code"], "name": r["supplier_name"], "products": 0})
        a["products"] += 1
    return sorted(agg.values(), key=lambda a: str(a["name"] or "").lower())


# --------------------------------------------------------------------------
# Section A -- Own Store
# --------------------------------------------------------------------------

_warming: set = set()


def warm_network(tenant_id, cfg):
    """Build the tenant-wide network on a background thread (once at a time),
    so the cross-store sections are ready by the time they are opened."""
    key = str(tenant_id).upper()
    if key in _warming:
        return
    _warming.add(key)

    def run():
        try:
            network(tenant_id, cfg)
        except Exception:  # pragma: no cover - best effort
            logger.exception("non-moving network warm-up failed")
        finally:
            _warming.discard(key)

    threading.Thread(target=run, name="nonmoving-warm", daemon=True).start()


def own_store(tenant_id, store_id, cfg, filters, sort, direction, page, page_size, refresh=False, all_rows=False):
    store = _store_of(tenant_id, store_id)
    rows, hit = _analysed(tenant_id, store, cfg, refresh)
    warm_network(tenant_id, cfg)
    shown = filter_rows(rows, **filters)
    if all_rows:
        page_rows, total, page, size = _page(shown, sort, direction, 1, None)
    else:
        page_rows, total, page, size = _page(shown, sort, direction, page, page_size)
    filtered_value = round(sum(r["cost_value"] for r in shown), 2)
    return {
        "store": store,
        "rows": page_rows,
        "total": total,
        "page": page,
        "page_size": size,
        "filtered_value": filtered_value,
        "filtered_qty": round(sum(r["stock"] for r in shown), 2),
        "kpis": store_kpis(rows),
        "by_class": class_summary(rows),
        "suppliers": _suppliers(rows),
        "refreshed_at": _stamp(hit["at"]),
        "query_seconds": hit.get("seconds"),
        "config": config_info(cfg),
    }


def product_detail(tenant_id, store_id, product_code, cfg):
    """One product: analysed row, batch-wise expiry, every store's movement and
    the transfer recommendations / blocks that involve it."""
    store = _store_of(tenant_id, store_id)
    net = network(tenant_id, cfg)
    sid = str(store["store_id"]).upper()
    code = str(product_code)
    row = net.rows.get(sid, {}).get(code)
    if row is None:
        raise HTTPException(status_code=404, detail="Product has no stock or recent sales in this store")
    batches = repo.product_batches(tenant_id, store["store_id"], code)
    stores = cross_store_rows(net, sid, code)
    recs, blocks = transfer_plan(net, cfg)
    involved = [r for r in recs if (r["source_store_id"] == sid and r["source_code"] == code)
                or (r["dest_store_id"] == sid and r["dest_code"] == code)]
    blocked = [b for b in blocks if b["store_id"] == sid and b["product_code"] == code]
    return {"store": store, "product": row, "batches": batches, "stores": stores,
            "transfers": involved, "transfer_blocks": blocked, "refreshed_at": _stamp(net.refreshed_at)}


def product_batches(tenant_id, store_id, product_code):
    store = _store_of(tenant_id, store_id)
    return {"store": store, "batches": repo.product_batches(tenant_id, store["store_id"], product_code)}


# --------------------------------------------------------------------------
# Section B -- Other Stores
# --------------------------------------------------------------------------

def _store_cell(net, sid, row, conf=None, ambiguous=False, current=False):
    s = net.meta.get(sid, {})
    return {
        "store_id": s.get("store_id", sid),
        "store_code": s.get("store_code"),
        "store_name": s.get("store_name"),
        "is_warehouse": bool(s.get("is_warehouse")),
        "current": current,
        "product_code": row["product_code"],
        "product_name": row["product_name"],
        "stock": row["stock"],
        "last_sale_date": row["last_sale_date"],
        "days_since_sale": row["days_since_sale"],
        "sales_30": row["sales_30"],
        "sales_90": row["sales_90"],
        "monthly_avg": round(row["sales_90"] / 3.0, 2),
        "cost_value": row["cost_value"],
        "classification": row["classification"],
        "classification_label": row["classification_label"],
        "expiry_status": row["expiry_status"],
        "mapping_confidence": conf,
        "ambiguous": ambiguous,
    }


def cross_store_rows(net, sid, code):
    row = net.rows.get(sid, {}).get(code)
    if row is None:
        return []
    out = [_store_cell(net, sid, row, current=True)]
    peers = net.peers(sid, code)
    for other, (pcode, conf, amb) in peers.items():
        out.append(_store_cell(net, other, net.rows[other][pcode], conf, amb))
    out[1:] = sorted(out[1:], key=lambda c: c["store_code"] or "")
    return out


def other_stores(tenant_id, store_id, cfg, search=None, scope="selling", sort="other_sales_30",
                 direction="desc", page=1, page_size=200, refresh=False, all_rows=False):
    """Products non-moving in THIS store, compared across the other stores.
    scope: selling = at least one other store sold it in 30 days (default);
           all = every non-moving product that is mapped to another store."""
    store = _store_of(tenant_id, store_id)
    net = network(tenant_id, cfg, refresh)
    sid = str(store["store_id"]).upper()
    q = (search or "").strip().lower()
    out = []
    for code, row in net.rows.get(sid, {}).items():
        if not row["non_moving"]:
            continue
        if q and not _text_match(row, q):
            continue
        peers = net.peers(sid, code)
        if not peers:
            continue
        cells = [_store_cell(net, o, net.rows[o][c], conf, amb) for o, (c, conf, amb) in peers.items()]
        selling = [c for c in cells if c["sales_30"] > 0]
        if scope != "all" and not selling:
            continue
        best = max(cells, key=lambda c: c["sales_30"])
        out.append({
            "product_code": code,
            "product_name": row["product_name"],
            "unit": row["unit"],
            "pack": row["pack"],
            "stock": row["stock"],
            "cost_value": row["cost_value"],
            "days_since_sale": row["days_since_sale"],
            "last_sale_date": row["last_sale_date"],
            "classification": row["classification"],
            "classification_label": row["classification_label"],
            "mapped_stores": len(cells),
            "active_stores": len(selling),
            "other_stock": round(sum(c["stock"] for c in cells), 2),
            "other_sales_30": round(sum(c["sales_30"] for c in cells), 2),
            "other_sales_90": round(sum(c["sales_90"] for c in cells), 2),
            "best_store": best["store_code"] if best["sales_30"] > 0 else None,
            "best_store_sales_30": best["sales_30"],
            "ambiguous": any(c["ambiguous"] for c in cells),
            "stores": sorted(cells, key=lambda c: c["store_code"] or ""),
        })
    page_rows, total, page, size = _page(out, sort, direction, 1 if all_rows else page,
                                         None if all_rows else page_size)
    return {"store": store, "rows": page_rows, "total": total, "page": page, "page_size": size,
            "stores": net.stores, "refreshed_at": _stamp(net.refreshed_at)}


# --------------------------------------------------------------------------
# Section C -- Transfer Opportunities (recommendations only)
# --------------------------------------------------------------------------

def _rate(row):
    return row["sales_90"] / 90.0 if row["sales_90"] > 0 else 0.0


def _transferable(row):
    """Stock that can safely move: the lower of store and batch stock (a
    disagreement is never resolved upward), minus expired and near-expiry
    batches."""
    base = min(row["stock"], row["batch_stock"])
    return max(0.0, base - row["expired_qty"] - row["near_expiry_qty"])


def _whole_packs(qty, sale_unit):
    if sale_unit and sale_unit > 1:
        return math.floor(qty / sale_unit + 1e-9) * sale_unit
    return math.floor(qty + 1e-9)


def source_excess(row, cfg: Config):
    """(excess qty, keep qty, transferable) for a candidate source."""
    avail = _transferable(row)
    keep = math.ceil(_rate(row) * cfg.source_keep_days) if row["classification"] not in NON_MOVING else 0
    return max(0.0, avail - keep), keep, avail


def dest_need(row, cfg: Config):
    """(need qty, target qty) for a candidate destination, or None + reason."""
    if not row["is_active"]:
        return None, "inactive product at destination"
    if row["sales_90"] <= 0:
        return None, "no sales in 90 days"
    if row["days_since_sale"] is None or row["days_since_sale"] > cfg.dest_active_days:
        return None, f"no sale in the last {cfg.dest_active_days} days"
    if row["bills_90"] < cfg.dest_min_bills:
        return None, f"sold on fewer than {cfg.dest_min_bills} bills in 90 days"
    target = math.ceil(_rate(row) * cfg.dest_cover_days)
    need = target - max(0.0, row["stock"])
    if need <= 0:
        return None, f"already holds {row['stock']:g} (>= {cfg.dest_cover_days} days of sales = {target:g})"
    return (need, target), None


def _rec(net, cfg, g, c, r, dg, dc, dr, qty, need, target, keep, avail, excess):
    unit_cost = r["cost_value"] / r["batch_stock"] if r["batch_stock"] > 0 else 0.0
    src, dst = net.meta.get(g, {}).get("store_code"), net.meta.get(dg, {}).get("store_code")
    age = "never sold" if r["days_since_sale"] is None else f"{r['days_since_sale']} days since last sale"
    return {
        "id": f"{g}|{c}|{dg}|{dc}",
        "source_store_id": g, "source_store": src, "source_code": c,
        "dest_store_id": dg, "dest_store": dst, "dest_code": dc,
        "product_name": r["product_name"], "unit": r["unit"], "pack": r["pack"], "sale_unit": r["sale_unit"],
        "source_stock": r["stock"], "source_batch_stock": r["batch_stock"],
        "source_transferable": round(avail, 2), "source_keep": keep,
        "source_classification": r["classification"], "source_classification_label": r["classification_label"],
        "source_days_since_sale": r["days_since_sale"],
        "source_expired_qty": r["expired_qty"], "source_near_expiry_qty": r["near_expiry_qty"],
        "source_earliest_expiry": r["earliest_expiry"],
        "dest_stock": dr["stock"], "dest_sales_30": dr["sales_30"], "dest_sales_90": dr["sales_90"],
        "dest_bills_90": dr["bills_90"], "dest_days_since_sale": dr["days_since_sale"],
        "dest_target": target, "dest_need": round(need, 2),
        "suggested_qty": qty, "suggested_packs": round(qty / (r["sale_unit"] or 1), 2),
        "source_after": round(r["stock"] - qty, 2), "dest_after": round(dr["stock"] + qty, 2),
        "transfer_value": round(unit_cost * qty, 2),
        "reason": (f"{src} {r['classification_label'].lower()} ({age}); {dst} sold {dr['sales_90']:g} in 90 days"
                   f" on {dr['bills_90']} bills and holds {dr['stock']:g}."),
        "calculation": (f"{dst} target = ceil({dr['sales_90']:g} / 90 x {cfg.dest_cover_days}) = {target:g};"
                        f" need = {target:g} - {dr['stock']:g} = {need:g}."
                        f" {src} transferable = min(stock {r['stock']:g}, batches {r['batch_stock']:g})"
                        f" - expired {r['expired_qty']:g} - near-expiry {r['near_expiry_qty']:g}"
                        f" - keep {keep:g} = {excess:g}."
                        f" Suggested = min(need, transferable) in whole packs of {r['sale_unit']:g} = {qty:g}."),
    }


_DEMAND_REASONS = ("no sales in", "no sale in the last", "sold on fewer", "already holds", "covered by")


def transfer_plan(net: Network, cfg: Config):
    """All recommendations for the tenant, plus the reason each non-moving
    source got none. Deterministic greedy allocation over DIRECT mapping edges:
    sources oldest-first (never sold first, then by days since sale), each
    filling its mapped destinations largest-need-first. Destination need is
    tracked across sources so it is never allocated twice."""
    recs, blocks = [], []
    need_left = {}

    def dest_state(dg, dc, dr):
        key = (dg, dc)
        if key not in need_left:
            need, why = dest_need(dr, cfg)
            need_left[key] = {"need": need[0], "target": need[1]} if need else {"need": 0.0, "why": why}
        return need_left[key]

    def block(g, c, r, reason, details=None):
        blocks.append({"store_id": g, "store_code": net.meta.get(g, {}).get("store_code"),
                       "product_code": c, "product_name": r["product_name"], "stock": r["stock"],
                       "cost_value": r["cost_value"], "classification": r["classification"],
                       "classification_label": r["classification_label"],
                       "days_since_sale": r["days_since_sale"], "reason": reason,
                       "details": details or []})

    sources = []
    for g, rows in net.rows.items():
        for c, r in rows.items():
            # Never pull stock that is selling (Active) or just arrived (New):
            # a source is idle (non-moving) or slow stock above its own cover.
            if not r["in_stock"] or r["classification"] in ("ACTIVE", "NEW"):
                continue
            excess, keep, avail = source_excess(r, cfg)
            if r["non_moving"] or excess > 0:
                sources.append((g, c, r, excess, keep, avail))
    sources.sort(key=lambda s: (-(s[2]["days_since_sale"] if s[2]["days_since_sale"] is not None else 10 ** 6),
                                -s[2]["cost_value"], s[0], s[1]))

    for g, c, r, excess, keep, avail in sources:
        nm = r["non_moving"]
        if not r["is_active"]:
            if nm:
                block(g, c, r, "inactive product at source")
            continue
        peers = net.peers(g, c)
        if not peers:
            if nm:
                block(g, c, r, "not mapped to any other store")
            continue
        if excess <= 0:
            if nm:
                block(g, c, r, "no transferable stock (expired / near-expiry / store and batch stock disagree)")
            continue
        candidates, reasons = [], []
        for dg, (dc, _conf, amb) in peers.items():
            dr = net.rows[dg][dc]
            code = net.meta.get(dg, {}).get("store_code")
            if amb:
                reasons.append((code, "product identity is ambiguous (a store maps to more than one product)"))
                continue
            if abs(dr["sale_unit"] - r["sale_unit"]) > 1e-9:
                reasons.append((code, f"pack size differs (sale unit {r['sale_unit']:g} vs {dr['sale_unit']:g})"))
                continue
            st = dest_state(dg, dc, dr)
            if st["need"] <= 0:
                reasons.append((code, st.get("why") or "covered by earlier recommendations"))
                continue
            candidates.append((dg, dc, dr, st))
        candidates.sort(key=lambda x: (-x[3]["need"], x[0]))
        remaining, made = excess, 0
        for dg, dc, dr, st in candidates:
            if remaining <= 0:
                break
            qty = _whole_packs(min(remaining, st["need"]), r["sale_unit"])
            if qty <= 0:
                reasons.append((net.meta.get(dg, {}).get("store_code"), "need is smaller than one pack"))
                continue
            recs.append(_rec(net, cfg, g, c, r, dg, dc, dr, qty, st["need"], st["target"], keep, avail, excess))
            remaining -= qty
            st["need"] -= qty
            made += 1
        if not made and nm:
            details = [f"{code}: {why}" for code, why in reasons]
            hard = sorted({why.split(" (")[0] for _, why in reasons if not why.startswith(_DEMAND_REASONS + ("need is smaller",))})
            if hard:
                block(g, c, r, hard[0], details)
            elif any(why.startswith("need is smaller") for _, why in reasons):
                block(g, c, r, "demand elsewhere is smaller than one pack", details)
            else:
                block(g, c, r, "no mapped store has verified demand needing stock", details)
    return recs, blocks


def transfers(tenant_id, store_id, cfg, direction="all", search=None, sort="transfer_value",
              order="desc", page=1, page_size=200, refresh=False, all_rows=False, ids=None):
    net = network(tenant_id, cfg, refresh)
    recs, blocks = transfer_plan(net, cfg)
    sid = str(store_id or "").upper()
    if sid:
        if direction == "out":
            recs = [r for r in recs if r["source_store_id"] == sid]
        elif direction == "in":
            recs = [r for r in recs if r["dest_store_id"] == sid]
        else:
            recs = [r for r in recs if sid in (r["source_store_id"], r["dest_store_id"])]
        blocks = [b for b in blocks if b["store_id"] == sid]
    if ids:
        wanted = set(ids)
        recs = [r for r in recs if r["id"] in wanted]
    q = (search or "").strip().lower()
    if q:
        recs = [r for r in recs if q in str(r["product_name"] or "").lower() or q in (r["source_code"], r["dest_code"])]
    reasons = {}
    for b in blocks:
        reasons[b["reason"]] = reasons.get(b["reason"], 0) + 1
    page_rows, total, page, size = _page(recs, sort, order, 1 if all_rows else page, None if all_rows else page_size)
    return {
        "rows": page_rows, "total": total, "page": page, "page_size": size,
        "total_qty": round(sum(r["suggested_qty"] for r in recs), 2),
        "total_value": round(sum(r["transfer_value"] for r in recs), 2),
        "blocked": sorted(({"reason": k, "products": v} for k, v in reasons.items()), key=lambda x: -x["products"]),
        "blocked_rows": blocks if all_rows else blocks[:500],
        "stores": net.stores, "refreshed_at": _stamp(net.refreshed_at), "config": config_info(cfg),
    }


# --------------------------------------------------------------------------
# Section D -- Stock Value & Expiry Risk / dashboard
# --------------------------------------------------------------------------

def dashboard(tenant_id, store_id, cfg, refresh=False, months=6):
    store = _store_of(tenant_id, store_id)
    net = network(tenant_id, cfg, refresh)
    sid = str(store["store_id"]).upper()
    recs, _ = transfer_plan(net, cfg)
    rows = list(net.rows.get(sid, {}).values())
    kpis = store_kpis(rows)
    kpis["transfer_opportunities"] = sum(1 for r in recs if r["source_store_id"] == sid)
    kpis["transfer_in_opportunities"] = sum(1 for r in recs if r["dest_store_id"] == sid)
    kpis["transfer_value"] = round(sum(r["transfer_value"] for r in recs if r["source_store_id"] == sid), 2)
    comparison = []
    for s in net.stores:
        k = str(s["store_id"]).upper()
        srows = list(net.rows.get(k, {}).values())
        sk = store_kpis(srows)
        sk.update({"store_id": s["store_id"], "store_code": s["store_code"], "store_name": s["store_name"],
                   "is_warehouse": bool(s.get("is_warehouse")), "current": k == sid,
                   "by_class": class_summary(srows),
                   "transfer_out": sum(1 for r in recs if r["source_store_id"] == k),
                   "transfer_in": sum(1 for r in recs if r["dest_store_id"] == k)})
        comparison.append(sk)
    expiry_rows = sorted((r for r in rows if r["in_stock"] and (r["expired_value"] > 0 or r["near_expiry_value"] > 0)),
                         key=lambda r: -(r["expired_value"] + r["near_expiry_value"]))
    return {
        "store": store,
        "kpis": kpis,
        "by_class": class_summary(rows),
        "stores": comparison,
        "monthly": repo.monthly_movement(tenant_id, store["store_id"], months),
        "expiry_top": expiry_rows[:50],
        "refreshed_at": _stamp(net.refreshed_at),
        "config": config_info(cfg),
    }


def review_rows(tenant_id, items, cfg):
    """Analysed rows for a manual-review list [{store_id, product_code}]."""
    net = network(tenant_id, cfg)
    out = []
    for it in items:
        sid = str(it.get("store_id") or "").upper()
        row = net.rows.get(sid, {}).get(str(it.get("product_code")))
        if row:
            out.append({**row, "store_code": net.meta.get(sid, {}).get("store_code"), "note": it.get("note")})
    return out
