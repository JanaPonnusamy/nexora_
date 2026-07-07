"""Product Intelligence Workspace — orchestration + pure consolidation maths.

The engine turns the anchor Refresh's VPL into a fully-calculated, cross-store
grid cached for the UI:

    Read anchor VPL (source list)
        -> Discover ACTIVE stores dynamically
        -> Resolve each product across stores via Common Product Mapping
        -> Collect each store's stock + suggested qty + movement metrics
        -> Consolidate  (SUM suggested; MAX(0, SUM suggested - SUM stock))
        -> Persist cache  (UI reads the cache only)

Consolidated formulae (never computed in the UI):

    consolidated_suggest  = SUM(store suggested qty)
    consolidated_purchase = MAX(0, SUM(store suggested qty) - SUM(store stock))
    transfer (internal)   = consolidated_suggest - consolidated_purchase
                          = the demand satisfiable from existing stock

Rows are NEVER removed — a product with purchase = 0 stays visible because
another store may hold the excess (internal-transfer opportunity).
"""

import uuid

from fastapi import HTTPException

from modules.procurement import intelligence_repository as repo


# --------------------------------------------------------------------------
# Cross-store resolution (Common Product Mapping — ProductCode is never a key)
# --------------------------------------------------------------------------

def _build_resolver(mappings):
    """Two directed lookups so a product mapped as either source or target of an
    edge resolves to the peer store's ProductCode."""
    by_source, by_target = {}, {}
    for m in mappings:
        src_s, tgt_s = m["source_store_id"], m["target_store_id"]
        src_c, tgt_c = m["source_product_code"], m["target_product_code"]
        method = m.get("match_method") or "MAPPED"
        if src_c is not None and tgt_c is not None:
            by_source[(src_s, str(src_c), tgt_s)] = (str(tgt_c), method)
            by_target[(tgt_s, str(tgt_c), src_s)] = (str(src_c), method)
    return by_source, by_target


def _resolve(by_source, by_target, anchor_store, code, target_store):
    """The target store's ProductCode for a product identified in the anchor
    store (or None when the product is not mapped there -> blank cell)."""
    if target_store == anchor_store:
        return (code, "ANCHOR")
    hit = by_source.get((anchor_store, code, target_store))
    if hit:
        return hit
    return by_target.get((anchor_store, code, target_store))


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def build_intelligence(tenant_id, refresh_id=None, created_by=None):
    """Build the Product Intelligence cache from the latest Refresh + VPL."""
    if not refresh_id:
        refresh_id = repo.latest_ready_refresh_for_tenant(tenant_id)
    if not refresh_id:
        raise HTTPException(
            status_code=404,
            detail="No generated Refresh found for this tenant. Generate a VPL first.",
        )

    refresh = repo.get_refresh(tenant_id, refresh_id)
    if not refresh:
        raise HTTPException(status_code=404, detail="Refresh not found")

    anchor_store = refresh.get("store_id")
    rolling_days = int(refresh.get("rolling_days") or 90) or 90

    anchor_products = repo.anchor_vpl_products(tenant_id, refresh_id)
    if not anchor_products:
        raise HTTPException(
            status_code=409,
            detail="The anchor Refresh has an empty VPL — nothing to consolidate.",
        )

    stores = repo.list_active_stores(tenant_id)
    store_ids = [s["store_id"] for s in stores]

    by_source, by_target = _build_resolver(repo.load_mappings(tenant_id, store_ids))

    # Per-store sources: each store's own suggested qty (from its latest Ready
    # VPL; the anchor store uses THIS refresh) + live stock / movement metrics.
    suggested_by_store, metrics_by_store = {}, {}
    for s in stores:
        sid = s["store_id"]
        sug_refresh = refresh_id if sid == anchor_store else repo.latest_ready_refresh_id(tenant_id, sid)
        suggested_by_store[sid] = repo.store_suggested_map(tenant_id, sug_refresh)
        metrics_by_store[sid] = repo.store_metrics(tenant_id, sid, rolling_days)

    anchor_metrics = metrics_by_store.get(anchor_store, {})
    anchor_last_pur = repo.anchor_last_purchase_rate(
        tenant_id, anchor_store, [p.get("product_code") for p in anchor_products]
    )

    build_id = str(uuid.uuid4())
    cache_rows, store_rows = [], []
    tot_sug = tot_pur = tot_trans = tot_stock = 0.0

    for ap in anchor_products:
        code = ap.get("product_code")
        if code is None:
            continue
        code = str(code)
        cache_id = str(uuid.uuid4())

        sum_sug = sum_stock = 0.0
        mapped = 0
        for s in stores:
            sid = s["store_id"]
            resolved = _resolve(by_source, by_target, anchor_store, code, sid)
            if resolved is None:
                continue  # not mapped in this store -> blank cell (no row)
            scode, method = resolved
            m = metrics_by_store.get(sid, {}).get(scode)
            sug = suggested_by_store.get(sid, {}).get(scode, 0.0) or 0.0
            stock = float(m["stock"]) if m and m.get("stock") is not None else 0.0

            mapped += 1
            sum_sug += sug
            sum_stock += stock
            store_rows.append({
                "cache_store_id": str(uuid.uuid4()),
                "cache_id": cache_id,
                "build_id": build_id,
                "tenant_id": tenant_id,
                "store_id": sid,
                "product_id": scode,
                "product_code": scode,
                "product_name": (m or {}).get("product_name") or ap.get("product_name"),
                "match_method": method,
                "stock_qty": stock,
                "suggested_qty": sug,
                "avg_sale": (m or {}).get("avg_sale"),
                "last_sale_date": (m or {}).get("last_sale_date"),
                "last_purchase_date": (m or {}).get("last_purchase_date"),
                "non_moving_days": (m or {}).get("non_moving_days"),
            })

        consolidated_suggest = round(sum_sug, 3)
        consolidated_purchase = round(max(0.0, sum_sug - sum_stock), 3)
        transfer = round(consolidated_suggest - consolidated_purchase, 3)

        am = anchor_metrics.get(code) or {}
        alp = anchor_last_pur.get(code) or {}
        cache_rows.append({
            "cache_id": cache_id,
            "build_id": build_id,
            "tenant_id": tenant_id,
            "refresh_id": refresh_id,
            "vpl_id": ap.get("virtual_product_id"),
            "common_product_id": str(uuid.uuid4()),
            "product_code": code,
            "product_name": ap.get("product_name"),
            "manufacturer_id": ap.get("manufacturer_id"),
            "consolidated_suggest_qty": consolidated_suggest,
            "consolidated_purchase_qty": consolidated_purchase,
            "consolidated_stock_qty": round(sum_stock, 3),
            "transfer_qty": transfer,
            "mapped_store_count": mapped,
            "mrp": ap.get("mrp") or am.get("mrp") or alp.get("mrp"),
            "ptr_cost": ap.get("ptr_cost") or am.get("ptr") or alp.get("purchaseprice"),
            "last_purchase_rate": alp.get("purchaseprice"),
            "margin": am.get("margin") or alp.get("Margin"),
            "offer_text": None,
        })

        tot_sug += consolidated_suggest
        tot_pur += consolidated_purchase
        tot_trans += transfer
        tot_stock += sum_stock

    header = {
        "build_id": build_id,
        "tenant_id": tenant_id,
        "refresh_id": refresh_id,
        "cycle_id": refresh.get("cycle_id"),
        "anchor_store_id": anchor_store,
        "product_count": len(cache_rows),
        "store_count": len(stores),
        "rolling_days": rolling_days,
        "total_suggest_qty": round(tot_sug, 3),
        "total_purchase_qty": round(tot_pur, 3),
        "total_transfer_qty": round(tot_trans, 3),
        "total_stock_qty": round(tot_stock, 3),
        "status": "Ready",
        "generated_by": created_by,
    }

    repo.save_build(header, cache_rows, store_rows)

    return {
        "build_id": build_id,
        "refresh_id": str(refresh_id),
        "anchor_store_id": anchor_store,
        "product_count": len(cache_rows),
        "store_count": len(stores),
        "total_suggest_qty": header["total_suggest_qty"],
        "total_purchase_qty": header["total_purchase_qty"],
        "total_transfer_qty": header["total_transfer_qty"],
        "total_stock_qty": header["total_stock_qty"],
    }


# --------------------------------------------------------------------------
# Reads (cache only)
# --------------------------------------------------------------------------

def _require_build(tenant_id, refresh_id):
    build = repo.latest_build(tenant_id, refresh_id)
    if not build:
        raise HTTPException(
            status_code=404,
            detail="No Product Intelligence cache yet. Build it from the latest Refresh.",
        )
    return build


def get_grid(tenant_id, refresh_id=None, search=None):
    """The dynamic grid: store columns + one consolidated row per product, each
    row carrying its per-store {suggested, stock, ...} cells (blank = absent)."""
    build = _require_build(tenant_id, refresh_id)
    build_id = build["build_id"]

    stores = repo.build_stores(build_id)
    rows = repo.grid_rows(build_id)
    cells = repo.grid_store_cells(build_id)

    by_cache = {}
    for c in cells:
        by_cache.setdefault(c["cache_id"], {})[c["store_id"]] = {
            "store_id": c["store_id"],
            "product_code": c["product_code"],
            "suggested_qty": c.get("suggested_qty"),
            "stock_qty": c.get("stock_qty"),
            "avg_sale": c.get("avg_sale"),
            "last_sale_date": c.get("last_sale_date"),
            "last_purchase_date": c.get("last_purchase_date"),
            "non_moving_days": c.get("non_moving_days"),
            "match_method": c.get("match_method"),
        }

    needle = (search or "").strip().lower()
    out_rows = []
    for r in rows:
        if needle:
            hay = f"{r.get('product_code') or ''} {r.get('product_name') or ''}".lower()
            if needle not in hay:
                continue
        r = dict(r)
        r["stores"] = by_cache.get(r["cache_id"], {})
        out_rows.append(r)

    return {
        "build": build,
        "stores": stores,
        "rows": out_rows,
        "summary": {
            "total_products": build.get("product_count"),
            "purchase_quantity": build.get("total_purchase_qty"),
            "transfer_quantity": build.get("total_transfer_qty"),
            "stock_quantity": build.get("total_stock_qty"),
            "suggest_quantity": build.get("total_suggest_qty"),
        },
    }


def get_detail(cache_id):
    """Per-product detail: consolidated values, commercial context and the full
    stock distribution across stores (feeds the detail panel + store charts)."""
    cache = repo.get_cache(cache_id)
    if not cache:
        raise HTTPException(status_code=404, detail="Product not found in cache")
    return {"product": cache, "stores": repo.cache_store_rows(cache_id)}


def get_stores(cache_id):
    """Dynamic per-store metrics for one product."""
    cache = repo.get_cache(cache_id)
    if not cache:
        raise HTTPException(status_code=404, detail="Product not found in cache")
    return {"cache_id": cache_id, "stores": repo.cache_store_rows(cache_id)}


def get_hover(cache_id, store_id):
    """On-demand hover payload for one store cell: last sale / purchase, sales +
    purchase history and non-moving days. The only history read in the module —
    it reuses the proven stock.usp_* procedures and is never called on load."""
    ctx = repo.cache_store_context(cache_id, store_id)
    if not ctx:
        return {
            "cache_id": cache_id, "store_id": store_id, "mapped": False,
            "sales_history": [], "purchase_history": [],
            "last_sale_date": None, "last_purchase_date": None, "non_moving_days": None,
        }
    tenant_id = ctx.get("tenant_id")
    product_code = ctx.get("product_code")
    sales, purchases = [], []
    if product_code is not None and str(product_code).strip().isdigit():
        sales = repo.sales_history(tenant_id, store_id, product_code)
        purchases = repo.purchase_history(tenant_id, store_id, product_code)
    return {
        "cache_id": cache_id,
        "store_id": store_id,
        "mapped": True,
        "product_code": product_code,
        "product_name": ctx.get("product_name"),
        "last_sale_date": ctx.get("last_sale_date"),
        "last_purchase_date": ctx.get("last_purchase_date"),
        "non_moving_days": ctx.get("non_moving_days"),
        "sales_history": sales,
        "purchase_history": purchases,
    }


def get_summary(tenant_id, refresh_id=None):
    build = _require_build(tenant_id, refresh_id)
    return {
        "build_id": build["build_id"],
        "refresh_id": build["refresh_id"],
        "generated_on": build.get("generated_on"),
        "total_products": build.get("product_count"),
        "store_count": build.get("store_count"),
        "purchase_quantity": build.get("total_purchase_qty"),
        "transfer_quantity": build.get("total_transfer_qty"),
        "stock_quantity": build.get("total_stock_qty"),
        "suggest_quantity": build.get("total_suggest_qty"),
    }
