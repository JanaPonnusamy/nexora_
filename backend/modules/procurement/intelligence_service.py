"""Product Intelligence — the NETWORK procurement decision engine.

This is not an analytics screen. It answers exactly one question:

    How much should the WAREHOUSE purchase for the entire network?

not "how much should the warehouse purchase based on its own sales".

Architecture
------------
The warehouse (NMW) buys for 5-6 stores. Every store has its own ProductCodes,
its own sales / purchase history, its own stock and its own VPL. There is NO
common ProductCode — the only relationship between stores is the Common Product
Mapping, whose deterministic edges are derived from sync.SupplierProductMatch by
joining on (SupplierCode, SupplierProductCode). Stores are NEVER joined on
ProductCode.

    Refresh (per store — the Console already runs it for every selected store)
        -> Store VPL  x N            (existing Decision Engine, reused as-is)
        -> UNION of every store VPL  == the product universe
        -> group into CANONICAL products via the mapping (union-find)
        -> consolidate demand + stock across the group
        -> Final warehouse purchase qty

The warehouse VPL is NOT the starting point — it is one input among N. A product
NMW has never sold is absent from NMW's VPL; if NMC sells 400/month it still
appears here, with real demand, and the warehouse still has to buy it.

Consolidated formulae (never computed in the UI)
-------------------------------------------------
Each store's suggested_qty is ALREADY net of that store's own stock (the Decision
Engine subtracts it), so network demand is a plain sum and stock is NOT netted a
second time:

    network_need   = SUM(store suggested qty)          # incl. the warehouse's own
    warehouse_stock= stock on hand at the warehouse
    transfer_qty   = MIN(warehouse_stock, network_need) # servable from the shelf
    purchase_qty   = network_need - transfer_qty        # what the warehouse buys

Worked example (NMW 20/10, NMA 5/40, NMC 8/55, NMS 0/60):
    need = 10+40+55+60 = 165; warehouse stock = 20
    transfer = 20; purchase = 145.

Rows are NEVER removed — a product with purchase = 0 stays visible because the
warehouse shelf can cover it (an internal-transfer opportunity).
"""

import uuid
from datetime import date

from fastapi import HTTPException

from modules.procurement import intelligence_repository as repo


# --------------------------------------------------------------------------
# Canonical product grouping (union-find over the Common Product Mapping)
# --------------------------------------------------------------------------
#
# A node is (store_id, product_code) — a product AS ONE STORE KNOWS IT. An edge
# is a mapping row. A canonical product is a connected component: the same real
# supplier line, however differently each store codes it.

class _DisjointSet:
    def __init__(self):
        self.parent = {}

    def find(self, node):
        self.parent.setdefault(node, node)
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != root:      # path compression
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _group_products(vpl_nodes, mappings):
    """Group every (store, product_code) node into canonical products.

    ``vpl_nodes`` are the products some store actually needs (the union of the
    store VPLs). Mapping edges pull in each store's own code for the same
    product — including stores that hold STOCK but need nothing, which is how the
    warehouse's shelf gets counted against another store's demand.

    Returns (components, edge_stats) where components is {root: [node, ...]},
    restricted to components containing at least one VPL node.
    """
    dsu = _DisjointSet()
    for node in vpl_nodes:
        dsu.find(node)

    edges = []
    for m in mappings:
        src = (m["source_store_id"], str(m["source_product_code"]))
        tgt = (m["target_store_id"], str(m["target_product_code"]))
        dsu.union(src, tgt)
        edges.append((src, m))

    # Confidence / method of a canonical product = its WEAKEST internal edge.
    edge_stats = {}
    for src, m in edges:
        root = dsu.find(src)
        stat = edge_stats.setdefault(root, {"confidence": None, "methods": set()})
        conf = m.get("confidence")
        if conf is not None:
            stat["confidence"] = conf if stat["confidence"] is None else min(stat["confidence"], conf)
        if m.get("match_method"):
            stat["methods"].add(m["match_method"])

    groups = {}
    for node in dsu.parent:
        groups.setdefault(dsu.find(node), []).append(node)

    # Keep only groups some store actually needs; a group of pure stock-holders
    # with no demand anywhere is not a procurement decision.
    roots_with_demand = {dsu.find(n) for n in vpl_nodes}
    components = {r: nodes for r, nodes in groups.items() if r in roots_with_demand}
    return components, edge_stats


def _priority(network_need, purchase_qty, stockout_stores):
    """Explainable, derived — never stored by hand.

        CRITICAL  a store is selling this and has run out
        HIGH      the warehouse has to buy (shelf cannot cover the network)
        MEDIUM    demand exists but the warehouse shelf covers it (transfer only)
        NONE      no network demand
    """
    if network_need <= 0:
        return "NONE", 0
    if stockout_stores > 0:
        return "CRITICAL", 4
    if purchase_qty > 0:
        return "HIGH", 3
    return "MEDIUM", 2


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def build_intelligence(tenant_id, warehouse_store_id, store_ids=None, created_by=None):
    """Consolidate every selected store's VPL into the network procurement grid.

    ``warehouse_store_id`` is the purchasing store the final quantity is for (the
    store whose Purchase Manager will place the order). ``store_ids`` are the
    stores that took part in the refresh run; when omitted every ACTIVE store with
    a generated VPL takes part.
    """
    if not warehouse_store_id:
        raise HTTPException(
            status_code=400,
            detail="warehouse_store_id is required — the network purchase quantity "
                   "is calculated FOR the purchasing warehouse.",
        )

    all_stores = repo.list_active_stores(tenant_id)
    if store_ids:
        wanted = {str(s) for s in store_ids} | {str(warehouse_store_id)}
        stores = [s for s in all_stores if s["store_id"] in wanted]
    else:
        stores = all_stores
    if not any(s["store_id"] == str(warehouse_store_id) for s in stores):
        raise HTTPException(
            status_code=400,
            detail="The warehouse store is not an active store of this tenant",
        )

    # ---- Each participating store's OWN VPL (built by the existing pipeline).
    participating, refresh_by_store, vpl_by_store = [], {}, {}
    for store in stores:
        sid = store["store_id"]
        refresh = repo.latest_ready_refresh(tenant_id, sid)
        if not refresh:
            continue           # store never refreshed — it cannot contribute demand
        refresh_by_store[sid] = refresh
        vpl_by_store[sid] = repo.store_vpl_products(tenant_id, refresh["refresh_id"])
        participating.append(store)

    if not participating:
        raise HTTPException(
            status_code=409,
            detail="No store has a generated VPL yet. Run a Refresh first.",
        )
    if not any(v for v in vpl_by_store.values()):
        raise HTTPException(
            status_code=409,
            detail="Every selected store's VPL is empty — nothing to consolidate.",
        )

    warehouse_id = str(warehouse_store_id)
    store_id_list = [s["store_id"] for s in participating]
    wh_refresh = refresh_by_store.get(warehouse_id)
    rolling_days = int(
        (wh_refresh or next(iter(refresh_by_store.values()))).get("rolling_days") or 90
    ) or 90

    # ---- The product universe: the UNION of every store's VPL (NOT one anchor).
    vpl_rows = {}          # (store_id, product_code) -> that store's VPL row
    for sid, rows in vpl_by_store.items():
        for row in rows:
            code = row.get("product_code")
            if code is not None:
                vpl_rows[(sid, str(code))] = row

    mappings = repo.load_mappings(tenant_id, store_id_list)
    components, edge_stats = _group_products(set(vpl_rows), mappings)

    supplier_identity = repo.load_supplier_identity(tenant_id, store_id_list)
    metrics_by_store = {
        sid: repo.store_metrics(tenant_id, sid, rolling_days) for sid in store_id_list
    }
    wh_last_purchase = repo.last_purchase_rates(tenant_id, warehouse_id)
    store_order = {s["store_id"]: i for i, s in enumerate(participating)}

    build_id = str(uuid.uuid4())
    cache_rows, store_rows = [], []
    tot_need = tot_pur = tot_trans = tot_stock = 0.0

    for root, nodes in components.items():
        # Only stores taking part in THIS build contribute (a mapping may point at
        # a store that was not refreshed).
        nodes = sorted(
            (n for n in nodes if n[0] in store_order),
            key=lambda n: store_order[n[0]],
        )
        if not nodes:
            continue

        cache_id = str(uuid.uuid4())
        network_need = global_stock = total_sales = total_purchased = 0.0
        stockouts = 0
        wh_node = wh_stock = wh_suggest = None
        rows_for_group = []

        for sid, code in nodes:
            vpl = vpl_rows.get((sid, code))
            metric = metrics_by_store.get(sid, {}).get(code) or {}

            # suggested comes ONLY from that store's VPL — its own decision engine
            # output, already net of its own stock. No VPL row = it needs nothing.
            suggested = float(vpl.get("suggested_qty") or 0.0) if vpl else 0.0
            stock = float(
                metric.get("stock")
                if metric.get("stock") is not None
                else (vpl.get("current_stock_qty") if vpl else 0.0) or 0.0
            )
            sales_qty = float(metric.get("sales_qty") or (vpl or {}).get("window_sales_qty") or 0.0)
            purchase_qty = float(metric.get("purchase_qty") or 0.0)
            is_warehouse = sid == warehouse_id

            network_need += suggested
            global_stock += stock
            total_sales += sales_qty
            total_purchased += purchase_qty
            if suggested > 0 and stock <= 0:
                stockouts += 1
            if is_warehouse:
                wh_node, wh_stock, wh_suggest = (sid, code), stock, suggested

            rows_for_group.append({
                "cache_store_id": str(uuid.uuid4()),
                "cache_id": cache_id,
                "build_id": build_id,
                "tenant_id": tenant_id,
                "store_id": sid,
                "product_id": code,
                "product_code": code,
                "product_name": (vpl or {}).get("product_name") or metric.get("product_name"),
                "match_method": "WAREHOUSE" if is_warehouse else "MAPPED",
                "stock_qty": stock,
                "suggested_qty": suggested,
                "avg_sale": metric.get("avg_sale"),
                "sales_qty": sales_qty,
                "purchase_qty": purchase_qty,
                "days_cover": (vpl or {}).get("days_cover"),
                "in_vpl": 1 if vpl else 0,
                "is_warehouse": 1 if is_warehouse else 0,
                "refresh_id": (refresh_by_store.get(sid) or {}).get("refresh_id"),
                "last_sale_date": metric.get("last_sale_date"),
                "last_purchase_date": metric.get("last_purchase_date"),
                "non_moving_days": metric.get("non_moving_days"),
            })

        # ---- The network decision. Store stock is NOT netted twice: each store's
        # suggested qty is already net of its own shelf. Only the warehouse's shelf
        # can serve the network, so only it reduces the purchase.
        warehouse_stock = float(wh_stock or 0.0)
        network_need = round(network_need, 3)
        transfer_qty = round(min(warehouse_stock, network_need), 3)
        purchase_qty = round(network_need - transfer_qty, 3)
        priority, priority_rank = _priority(network_need, purchase_qty, stockouts)

        # Identity: prefer how the WAREHOUSE knows the product (that is the code
        # the purchase order is placed with); otherwise the first store that has it.
        identity_node = wh_node or nodes[0]
        identity_vpl = vpl_rows.get(identity_node) or {}
        identity_metric = metrics_by_store.get(identity_node[0], {}).get(identity_node[1]) or {}
        supplier = (
            supplier_identity.get(wh_node)
            or next((supplier_identity[n] for n in nodes if n in supplier_identity), {})
        )
        stat = edge_stats.get(root, {})
        methods = stat.get("methods") or set()
        wh_rate = wh_last_purchase.get(wh_node[1]) if wh_node else {}

        cache_rows.append({
            "cache_id": cache_id,
            "build_id": build_id,
            "tenant_id": tenant_id,
            "refresh_id": (wh_refresh or refresh_by_store[identity_node[0]])["refresh_id"],
            "vpl_id": identity_vpl.get("virtual_product_id"),
            "common_product_id": str(uuid.uuid4()),
            "product_code": identity_node[1],
            "product_name": identity_vpl.get("product_name") or identity_metric.get("product_name"),
            "manufacturer_id": identity_vpl.get("manufacturer_id"),
            "supplier_code": supplier.get("supplier_code"),
            "supplier_product_code": supplier.get("supplier_product_code"),
            "supplier_product_name": supplier.get("supplier_product_name"),
            "consolidated_suggest_qty": network_need,
            "consolidated_purchase_qty": purchase_qty,
            "consolidated_stock_qty": round(global_stock, 3),
            "transfer_qty": transfer_qty,
            "mapped_store_count": len(rows_for_group),
            "warehouse_stock_qty": warehouse_stock,
            # NULL = the warehouse does not stock this product at all. The network
            # still needs it, so it stays on the grid and the buyer sees the gap.
            "warehouse_product_code": wh_node[1] if wh_node else None,
            "warehouse_suggest_qty": float(wh_suggest or 0.0),
            "total_sales_qty": round(total_sales, 3),
            "total_purchase_qty": round(total_purchased, 3),
            "priority": priority,
            "priority_rank": priority_rank,
            "stockout_store_count": stockouts,
            "confidence": stat.get("confidence"),
            "match_method": "SUPPLIER" if methods == {"SUPPLIER"} else (
                sorted(methods)[0] if methods else None
            ),
            "mrp": identity_vpl.get("mrp") or identity_metric.get("mrp") or (wh_rate or {}).get("mrp"),
            "ptr_cost": identity_vpl.get("ptr_cost") or identity_metric.get("ptr"),
            "last_purchase_rate": (wh_rate or {}).get("purchaseprice"),
            "margin": identity_metric.get("margin") or (wh_rate or {}).get("Margin"),
            "offer_text": None,
        })
        store_rows.extend(rows_for_group)

        tot_need += network_need
        tot_pur += purchase_qty
        tot_trans += transfer_qty
        tot_stock += global_stock

    header = {
        "build_id": build_id,
        "tenant_id": tenant_id,
        "refresh_id": (wh_refresh or next(iter(refresh_by_store.values())))["refresh_id"],
        "cycle_id": (wh_refresh or {}).get("cycle_id"),
        "anchor_store_id": warehouse_id,
        "warehouse_store_id": warehouse_id,
        "product_count": len(cache_rows),
        "store_count": len(participating),
        "rolling_days": rolling_days,
        "total_need_qty": round(tot_need, 3),
        "total_suggest_qty": round(tot_need, 3),
        "total_purchase_qty": round(tot_pur, 3),
        "total_transfer_qty": round(tot_trans, 3),
        "total_stock_qty": round(tot_stock, 3),
        "status": "Ready",
        "generated_by": created_by,
    }

    build_stores = [{
        "build_store_id": str(uuid.uuid4()),
        "build_id": build_id,
        "tenant_id": tenant_id,
        "store_id": s["store_id"],
        "refresh_id": refresh_by_store[s["store_id"]]["refresh_id"],
        "is_warehouse": 1 if s["store_id"] == warehouse_id else 0,
        "vpl_product_count": len(vpl_by_store.get(s["store_id"]) or []),
        "vpl_generated_on": refresh_by_store[s["store_id"]].get("generation_completed_at"),
    } for s in participating]

    repo.save_build(header, build_stores, cache_rows, store_rows)

    return {
        "build_id": build_id,
        "warehouse_store_id": warehouse_id,
        "product_count": len(cache_rows),
        "store_count": len(participating),
        "stores": [{
            "store_id": b["store_id"],
            "is_warehouse": bool(b["is_warehouse"]),
            "vpl_product_count": b["vpl_product_count"],
        } for b in build_stores],
        "total_need_qty": header["total_need_qty"],
        "total_purchase_qty": header["total_purchase_qty"],
        "total_transfer_qty": header["total_transfer_qty"],
        "total_stock_qty": header["total_stock_qty"],
    }


# --------------------------------------------------------------------------
# Reads (cache only)
# --------------------------------------------------------------------------

def _require_build(tenant_id, build_id=None, warehouse_store_id=None):
    build = repo.latest_build(tenant_id, build_id, warehouse_store_id)
    if not build:
        raise HTTPException(
            status_code=404,
            detail="No Product Intelligence build yet. Build it from the latest Refresh.",
        )
    return build


def get_grid(tenant_id, build_id=None, warehouse_store_id=None, search=None):
    """The grid: one row per CANONICAL supplier product, each carrying its
    per-store cells (a store with no cell simply does not stock it)."""
    build = _require_build(tenant_id, build_id, warehouse_store_id)
    bid = build["build_id"]

    stores = repo.build_stores(bid)
    rows = repo.grid_rows(bid)
    cells = repo.grid_store_cells(bid)

    by_cache = {}
    for c in cells:
        by_cache.setdefault(c["cache_id"], {})[c["store_id"]] = c

    needle = (search or "").strip().lower()
    out_rows = []
    for r in rows:
        if needle:
            hay = (
                f"{r.get('product_code') or ''} {r.get('product_name') or ''} "
                f"{r.get('supplier_product_name') or ''} "
                f"{r.get('supplier_product_code') or ''}"
            ).lower()
            if needle not in hay:
                continue
        r = dict(r)
        r["stores"] = by_cache.get(r["cache_id"], {})
        out_rows.append(r)

    return {
        "build": build,
        "stores": stores,
        "rows": out_rows,
        "summary": _summary(build),
    }


def get_detail(cache_id):
    """Per-product detail: the network decision + every store's position. NO
    transaction history is read here — the detail panel loads history for the ONE
    store the user selects (see get_store_history)."""
    cache = repo.get_cache(cache_id)
    if not cache:
        raise HTTPException(status_code=404, detail="Product not found in this build")
    return {"product": cache, "stores": repo.cache_store_rows(cache_id)}


def get_stores(cache_id):
    """The stores this canonical product exists in (the detail store selector)."""
    cache = repo.get_cache(cache_id)
    if not cache:
        raise HTTPException(status_code=404, detail="Product not found in this build")
    return {"cache_id": cache_id, "stores": repo.cache_store_rows(cache_id)}


def get_store_history(cache_id, store_id, months=12):
    """History for ONE store only — sales, purchases and the monthly chart for the
    store the user has selected. Never loads every store at once: switching store
    loads only that store's transactions."""
    ctx = repo.cache_store_context(cache_id, store_id)
    if not ctx:
        return {
            "cache_id": cache_id, "store_id": store_id, "mapped": False,
            "sales_history": [], "purchase_history": [], "monthly_sales": [],
        }
    tenant_id = ctx.get("tenant_id")
    product_code = ctx.get("product_code")
    sales = purchases = monthly = []
    if product_code is not None and str(product_code).strip().isdigit():
        sales = repo.sales_history(tenant_id, store_id, product_code)
        purchases = repo.purchase_history(tenant_id, store_id, product_code)
        monthly = repo.monthly_sales(tenant_id, store_id, product_code, months)
    return {
        "cache_id": cache_id,
        "store_id": store_id,
        "mapped": True,
        "product_code": product_code,
        "product_name": ctx.get("product_name"),
        "stock_qty": ctx.get("stock_qty"),
        "suggested_qty": ctx.get("suggested_qty"),
        "sales_qty": ctx.get("sales_qty"),
        "purchase_qty": ctx.get("purchase_qty"),
        "avg_sale": ctx.get("avg_sale"),
        "in_vpl": ctx.get("in_vpl"),
        "last_sale_date": ctx.get("last_sale_date"),
        "last_purchase_date": ctx.get("last_purchase_date"),
        "non_moving_days": ctx.get("non_moving_days"),
        "sales_history": sales,
        "purchase_history": purchases,
        "monthly_sales": monthly,
    }


def get_store_charts(cache_id, months=4):
    """EVERY store's last-``months`` transaction chart, in ONE payload.

    Each store is resolved INDEPENDENTLY by ProductName — exactly how the legacy
    VB.NET analyser worked when it opened each store's database on its own. The
    mapping is deliberately not used here, so a store's chart never disappears
    because a mapping edge is missing.

    Returns a uniform month axis shared by every store, so the charts can be laid
    out side by side and read against each other at a glance (all visible at once,
    no scrolling).
    """
    cache = repo.get_cache(cache_id)
    if not cache:
        raise HTTPException(status_code=404, detail="Product not found in this build")

    tenant_id = cache["tenant_id"]
    months = max(1, min(int(months or 4), 24))
    stores = repo.build_stores(cache["build_id"])
    store_ids = [s["store_id"] for s in stores]

    resolved = repo.resolve_by_product_name(tenant_id, store_ids, cache.get("product_name"))
    pairs = [(sid, (resolved.get(sid) or {}).get("product_code")) for sid in store_ids]
    rows = repo.monthly_transactions(tenant_id, pairs, months)
    transfers = repo.monthly_transfers(tenant_id, pairs, months)

    # A shared, gap-free month axis (a month with no transaction is a real zero —
    # it must still occupy its slot, or the charts cannot be compared).
    today = date.today()
    axis = []
    for back in range(months - 1, -1, -1):
        year, month = divmod((today.year * 12 + today.month - 1) - back, 12)
        axis.append(f"{year:04d}-{month + 1:02d}")

    by_store = {}
    for r in rows:
        by_store.setdefault(r["store_id"], {})[r["period"]] = r
    xfer_by_store = {}
    for r in transfers:
        xfer_by_store.setdefault(r["store_id"], {})[r["period"]] = r

    series = []
    for store in stores:
        sid = store["store_id"]
        hit = resolved.get(sid)
        points = by_store.get(sid, {})
        xfers = xfer_by_store.get(sid, {})
        series.append({
            "store_id": sid,
            "store_code": store.get("store_code"),
            "store_name": store.get("store_name"),
            "is_warehouse": bool(store.get("is_warehouse")),
            "product_code": (hit or {}).get("product_code"),
            "product_name": (hit or {}).get("product_name"),
            "found": hit is not None,
            # Inventory ADDED = purchase + transfer in (the stacked bar);
            # inventory REMOVED = sales (overlay) + transfer out (indicator).
            "points": [{
                "period": p,
                "sales_qty": float((points.get(p) or {}).get("sales_qty") or 0.0),
                "purchase_qty": float((points.get(p) or {}).get("purchase_qty") or 0.0),
                "transfer_in": float((xfers.get(p) or {}).get("transfer_in") or 0.0),
                "transfer_out": float((xfers.get(p) or {}).get("transfer_out") or 0.0),
            } for p in axis],
        })

    return {
        "cache_id": cache_id,
        "product_name": cache.get("product_name"),
        "months": months,
        "axis": axis,
        "series": series,
    }


def _summary(build):
    return {
        "build_id": build["build_id"],
        "warehouse_store_id": build.get("warehouse_store_id"),
        "generated_on": build.get("generated_on"),
        "total_products": build.get("product_count"),
        "store_count": build.get("store_count"),
        "need_quantity": build.get("total_need_qty") or build.get("total_suggest_qty"),
        "purchase_quantity": build.get("total_purchase_qty"),
        "transfer_quantity": build.get("total_transfer_qty"),
        "stock_quantity": build.get("total_stock_qty"),
    }


def get_summary(tenant_id, build_id=None, warehouse_store_id=None):
    return _summary(_require_build(tenant_id, build_id, warehouse_store_id))


# --------------------------------------------------------------------------
# Refresh -> Store VPL (x N) -> Build, in one action
# --------------------------------------------------------------------------

def refresh_and_build(tenant_id, warehouse_store_id, store_ids, rolling_days=90,
                      min_days=7, max_days=30, created_by=None):
    """The whole procurement model in one call, exactly as the cockpit states it:

        selected stores -> Refresh EVERY store -> Store VPL x N
                        -> merge on the Common Product Mapping
                        -> network purchase recommendation

    Each store is refreshed through the EXISTING pipeline (sync -> business cycle
    -> Refresh -> Decision Engine -> VPL); nothing about the engine is duplicated
    here. A store whose refresh fails is reported and skipped — the build still
    consolidates the stores that succeeded, so one bad store never blocks the
    buyer's whole session.
    """
    from modules.procurement import pipeline_service

    targets = list(dict.fromkeys([*(store_ids or []), str(warehouse_store_id)]))
    refreshed, failed = [], []
    for sid in targets:
        try:
            result = pipeline_service.run(
                tenant_id, sid, rolling_days, min_days, max_days, created_by)
            refreshed.append({
                "store_id": sid,
                "refresh_id": result["refresh_id"],
                "vpl_product_count": result["generated_product_count"],
            })
        except Exception as exc:                      # one store must not sink the run
            failed.append({"store_id": sid, "error": str(exc)})

    build = build_intelligence(tenant_id, warehouse_store_id, targets, created_by)
    build["refreshed"] = refreshed
    build["failed"] = failed
    return build


# --------------------------------------------------------------------------
# Mode 2 — Supplier Offer Intelligence
# --------------------------------------------------------------------------

def supplier_offers(tenant_id, warehouse_store_id, supplier_code, build_id=None,
                    only_available=True, search=None):
    """What the supplier is offering, read against the NETWORK.

        supplier stock line -> the warehouse's ProductCode (SupplierProductMatch,
        resolved at import; a manual inline link overrides it)
                            -> the canonical product in the intelligence build
                            -> network need / purchase / transfer + every store

    An offered line that never resolved to a ProductCode is NOT hidden: it comes
    back with mapped=false and the UI puts an Assign button in the row. That is
    the whole point of the mode — the buyer maps it without leaving the screen.

    Everything except the supplier's own file comes from the Intelligence cache;
    no transaction table is touched.
    """
    build = _require_build(tenant_id, build_id, warehouse_store_id)
    bid = build["build_id"]

    stores = repo.build_stores(bid)
    rows = repo.grid_rows(bid)
    cells = repo.grid_store_cells(bid)

    by_cache = {}
    for c in cells:
        by_cache.setdefault(c["cache_id"], {})[c["store_id"]] = c

    # The build knows each canonical product by the WAREHOUSE's ProductCode —
    # which is exactly the code the supplier line resolves to.
    by_wh_code = {}
    for r in rows:
        code = r.get("warehouse_product_code")
        if code is not None:
            by_wh_code.setdefault(str(code), r)

    lines = repo.supplier_stock_lines(
        tenant_id, warehouse_store_id, supplier_code, only_available)

    needle = (search or "").strip().lower()
    out, mapped_count, unmapped_count = [], 0, 0
    for line in lines:
        if needle:
            hay = (
                f"{line.get('supplier_product_name') or ''} "
                f"{line.get('supplier_product_code') or ''} "
                f"{line.get('product_name') or ''} {line.get('product_code') or ''}"
            ).lower()
            if needle not in hay:
                continue

        code = line.get("product_code")
        intel = by_wh_code.get(str(code)) if code is not None else None
        mapped = code is not None
        if mapped:
            mapped_count += 1
        else:
            unmapped_count += 1

        row = dict(line)
        row["mapped"] = mapped
        # in_network = mapped AND the network actually needs it (it is in a build
        # row). Mapped-but-not-in-the-build = nobody has demand: offer, no need.
        row["in_network"] = intel is not None
        row["cache_id"] = (intel or {}).get("cache_id")
        row["consolidated_suggest_qty"] = (intel or {}).get("consolidated_suggest_qty") or 0
        row["consolidated_purchase_qty"] = (intel or {}).get("consolidated_purchase_qty") or 0
        row["transfer_qty"] = (intel or {}).get("transfer_qty") or 0
        row["consolidated_stock_qty"] = (intel or {}).get("consolidated_stock_qty") or 0
        row["mapped_store_count"] = (intel or {}).get("mapped_store_count") or 0
        row["priority"] = (intel or {}).get("priority")
        row["priority_rank"] = (intel or {}).get("priority_rank") or 0
        row["confidence"] = (intel or {}).get("confidence")
        row["stores"] = by_cache.get((intel or {}).get("cache_id"), {}) if intel else {}
        out.append(row)

    # Unmapped lines float to the top under a needed line: they are the buyer's
    # actionable backlog, and an offer nobody can see is an offer that is missed.
    out.sort(key=lambda r: (
        -(r["priority_rank"] or 0),
        0 if not r["mapped"] else 1,
        -(r["consolidated_purchase_qty"] or 0),
        (r.get("supplier_product_name") or ""),
    ))

    return {
        "build": build,
        "stores": stores,
        "supplier_code": supplier_code,
        "rows": out,
        "summary": {
            "offered_lines": len(out),
            "mapped_lines": mapped_count,
            "unmapped_lines": unmapped_count,
            "purchase_quantity": round(
                sum(float(r["consolidated_purchase_qty"] or 0) for r in out), 3),
        },
    }


def list_offer_suppliers(tenant_id, warehouse_store_id):
    """Suppliers with imported live stock for the warehouse (the mode's picker)."""
    return {"suppliers": repo.suppliers_with_stock(tenant_id, warehouse_store_id)}


def resolve_assignment(tenant_id, warehouse_store_id, product_code, build_id=None):
    """Preview the Assign: given the warehouse product the buyer picked, which of
    the other stores already resolve automatically through the Common Product
    Mapping, and which need a manual pick."""
    build = _require_build(tenant_id, build_id, warehouse_store_id)
    stores = repo.build_stores(build["build_id"])
    others = [s["store_id"] for s in stores if s["store_id"] != str(warehouse_store_id)]
    resolved = repo.resolve_mapped_stores(
        tenant_id, str(warehouse_store_id), str(product_code), others)
    return {
        "product_code": str(product_code),
        "stores": [{
            "store_id": s["store_id"],
            "store_code": s.get("store_code"),
            "store_name": s.get("store_name"),
            "is_warehouse": bool(s.get("is_warehouse")),
            "product_code": (resolved.get(s["store_id"]) or {}).get("product_code"),
            "product_name": (resolved.get(s["store_id"]) or {}).get("product_name"),
            "auto": s["store_id"] in resolved,
        } for s in stores if s["store_id"] != str(warehouse_store_id)],
    }


def assign_supplier_product(tenant_id, warehouse_store_id, supplier_code,
                            supplier_product_code, supplier_product_name,
                            product_code, store_assignments=None, actor=None):
    """Map an unmapped supplier line, inline, in two persisted steps:

      1. supplier line -> the WAREHOUSE ProductCode (procurement.supplier_product_link,
         which also repoints the already-imported supplier_stock rows so the row
         refreshes immediately and the link survives the next file import).
      2. warehouse ProductCode -> each OTHER store's ProductCode, written as
         MANUAL/APPROVED edges through the SAME dbo.product_mapping table the
         mapping module owns. Stores the mapping already resolves are written
         too — making the edge explicit costs nothing and the caller may have
         corrected one.

    The consolidated quantities only change on the next build (the grid is a
    cache, by design), so the response says what the row now resolves to and the
    UI refreshes just that row.
    """
    if not product_code:
        raise HTTPException(status_code=400, detail="product_code is required")

    warehouse = repo.get_store_product(tenant_id, warehouse_store_id, product_code)
    if not warehouse:
        raise HTTPException(
            status_code=404,
            detail="That ProductCode does not exist in the warehouse's catalogue",
        )

    repo.save_supplier_link(
        tenant_id, warehouse_store_id, supplier_code, supplier_product_code,
        supplier_product_name, warehouse["product_code"], warehouse.get("product_name"),
        actor,
    )

    written = []
    for a in (store_assignments or []):
        target_store = str(a.get("store_id") or "")
        target_code = a.get("product_code")
        if not target_store or not target_code or target_store == str(warehouse_store_id):
            continue
        target = repo.get_store_product(tenant_id, target_store, target_code)
        if not target:
            continue
        repo.save_manual_mapping(
            tenant_id,
            str(warehouse_store_id), warehouse["product_code"], warehouse.get("product_name"),
            target_store, target["product_code"], target.get("product_name"),
            actor,
        )
        written.append({
            "store_id": target_store,
            "product_code": target["product_code"],
            "product_name": target.get("product_name"),
        })

    return {
        "supplier_code": supplier_code,
        "supplier_product_code": supplier_product_code,
        "product_code": warehouse["product_code"],
        "product_name": warehouse.get("product_name"),
        "mapped_stores": written,
        # Consolidation is a cached build: the network numbers for this product
        # appear after the next build, not on this response.
        "rebuild_required": True,
    }
