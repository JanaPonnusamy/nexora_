"""Network Movement Intelligence — orchestration.

Answers one question, for a product a store already stocks or sells:

    How does the SAME canonical product move across every other active store
    in this tenant right now?

This is informational only. It never runs decision_rules.evaluate, never
writes procurement_virtual_products, and never changes suggested_qty, movement
class, stock status or supplier recommendation for any store. Those stay
exactly as the Decision Engine computes them.

Reuse, not a second engine:
  * Canonical product grouping reuses intelligence_service._DisjointSet — the
    SAME union-find class Product Intelligence already uses over the SAME
    dbo.product_mapping edges. The grouping PREDICATE differs on purpose (see
    _group_by_presence below) because the universe differs: Product Intelligence
    groups products some store's VPL currently needs; network movement groups
    products ANY active store has real sales/stock presence on, because a
    locally NON-MOVING product (zero sales) is structurally excluded from that
    store's own VPL (decision_rules.evaluate: avg<=0 -> EXCLUDED_NOT_SELLING) —
    it would never appear here at all if we only looked at VPL demand.
  * Movement classification reuses decision_rules.movement_class verbatim — the
    SAME FAST/MEDIUM/SLOW/NONMOVING thresholds local movement uses, applied to
    network-pooled avg_daily_sales instead of one store's own.
  * Performance pattern reuses intelligence_repository.store_metrics — one bulk
    query per active store (never per product), the same shape
    intelligence_service.py already uses.
"""

import logging
import threading
import uuid

from modules.procurement import decision_rules as rules
from modules.procurement import network_movement_repository as repo
from modules.procurement.intelligence_service import _DisjointSet

logger = logging.getLogger("procurement.network_movement")

# Each store's Refresh fires a tenant-wide recompute on its own background
# thread (orchestration_service). Several stores refreshing close together
# would otherwise start overlapping ~4-minute recomputes for the SAME tenant,
# racing on network_movement_repository.replace_all's delete+insert. A simple
# per-tenant non-blocking lock coalesces that into "one run at a time, per
# tenant" — a skipped run is harmless, the next Refresh (or a manual rebuild)
# recomputes anyway.
_tenant_locks: dict[str, threading.Lock] = {}
_tenant_locks_guard = threading.Lock()


def _lock_for(tenant_id: str) -> threading.Lock:
    with _tenant_locks_guard:
        return _tenant_locks.setdefault(tenant_id, threading.Lock())

# Same platform defaults decision_rules.DecisionParameters uses for
# classification (PR-BR-010) — min_days/max_days are irrelevant to
# movement_class() but DecisionParameters requires values, so pass 1/1
# (never used, never persisted, never affects sizing).
_CLASS_PARAMS = rules.DecisionParameters(rolling_days=90, min_days=1.0, max_days=1.0)


def _group_by_presence(nodes, mappings):
    """Union-find grouping restricted to products with REAL presence (sales or
    stock) at at least one store — not "some store's VPL needs it" (Product
    Intelligence's predicate), because a genuinely non-moving product is never
    in any VPL to begin with. Ambiguous/unmapped products are never merged:
    a node with no mapping edge simply forms its own single-store component."""
    dsu = _DisjointSet()
    for node in nodes:
        dsu.find(node)

    edges = []
    for m in mappings:
        src = (m["source_store_id"], str(m["source_product_code"]))
        tgt = (m["target_store_id"], str(m["target_product_code"]))
        if src not in dsu.parent and tgt not in dsu.parent:
            continue  # neither side has presence — nothing to group
        dsu.union(src, tgt)
        edges.append((src, m))

    edge_stats = {}
    for src, m in edges:
        root = dsu.find(src)
        stat = edge_stats.setdefault(root, {"confidence": None})
        conf = m.get("confidence")
        if conf is not None:
            stat["confidence"] = conf if stat["confidence"] is None else min(stat["confidence"], conf)

    groups = {}
    for node in dsu.parent:
        groups.setdefault(dsu.find(node), []).append(node)
    return groups, edge_stats


def _build_rows(tenant_id, groups, edge_stats, metrics_by_store, rolling_days):
    """Pure aggregation: canonical groups + per-store metrics -> persistable
    rows. No I/O — kept separate from refresh_network_movement() so the
    classification/aggregation math is unit-testable without a database."""
    rows = []
    for root, group_nodes in groups.items():
        # A single-store component (no mapping edge reached it) has nothing to
        # say beyond what the store's own local movement_class already shows —
        # skip it rather than writing a trivial "network == local" row for
        # every unmapped product in the catalogue (avoids unnecessary rows/
        # write volume; Case E of the design review: network equals local
        # context here, so there is nothing new to surface).
        if len(group_nodes) < 2:
            continue

        network_sales_qty = 0.0
        network_stock_qty = 0.0
        last_sale_date = None
        active = fast = medium = slow = non_moving = 0
        node_data = {}  # (sid, code) -> (sales_qty, stock, avg_sale, last_sale, local_class)

        for (sid, code) in group_nodes:
            m = metrics_by_store.get(sid, {}).get(code) or {}
            sales_qty = float(m.get("sales_qty") or 0.0)
            stock = float(m.get("stock") or 0.0)
            avg_sale = float(m.get("avg_sale") or 0.0)
            node_last_sale = m.get("last_sale_date")

            network_sales_qty += sales_qty
            network_stock_qty += stock
            if node_last_sale is not None:
                last_sale_date = node_last_sale if last_sale_date is None else max(last_sale_date, node_last_sale)
            if sales_qty > 0:
                active += 1

            # Read-only classification snapshot for THIS store's own node —
            # reuses decision_rules.movement_class verbatim, same as local
            # movement classification, but is NOT the VPL's authoritative
            # movement_class (that stays decision_service's alone).
            mclass = rules.movement_class(avg_sale, _CLASS_PARAMS)
            node_data[(sid, code)] = (sales_qty, stock, avg_sale, node_last_sale, mclass)
            if mclass == "FAST":
                fast += 1
            elif mclass == "MEDIUM":
                medium += 1
            elif mclass == "SLOW":
                slow += 1
            else:
                non_moving += 1

        network_avg_daily_sales = network_sales_qty / rolling_days if rolling_days else 0.0
        network_movement_class = rules.movement_class(network_avg_daily_sales, _CLASS_PARAMS)
        confidence = edge_stats.get(root, {}).get("confidence")
        canonical_product_id = uuid.uuid4()  # one label per group, no FK target

        for (sid, code) in group_nodes:
            local_sales, local_stock, local_avg, local_last_sale, local_class = node_data[(sid, code)]
            rows.append({
                "tenant_id": tenant_id,
                "store_id": sid,
                "store_product_code": code,
                "canonical_product_id": canonical_product_id,
                "network_movement_class": network_movement_class,
                "network_avg_daily_sales": round(network_avg_daily_sales, 4),
                "network_sales_qty": round(network_sales_qty, 3),
                "network_stock_qty": round(network_stock_qty, 3),
                "network_last_sale_date": last_sale_date,
                "mapped_store_count": len(group_nodes),
                "active_store_count": active,
                "fast_store_count": fast,
                "medium_store_count": medium,
                "slow_store_count": slow,
                "non_moving_store_count": non_moving,
                "confidence": confidence,
                "rolling_days": rolling_days,
                "local_sales_qty": round(local_sales, 3),
                "local_avg_daily_sales": round(local_avg, 4),
                "local_stock_qty": round(local_stock, 3),
                "local_last_sale_date": local_last_sale,
                "local_movement_class": local_class,
            })
    return rows


def refresh_network_movement(tenant_id: str) -> dict:
    """Recompute the network movement cache for every active store in the
    tenant. Called after any store's Refresh publishes (orchestration_service);
    safe to call directly for a manual rebuild. Never raises past the caller
    without being caught there — this is an informational side-feature, not
    part of the procurement-critical path.

    Coalesces overlapping calls for the SAME tenant (see _tenant_locks): if a
    run is already in progress, this call is a no-op rather than a second
    concurrent ~4-minute recompute racing the first on the same cache rows."""
    lock = _lock_for(tenant_id)
    if not lock.acquire(blocking=False):
        logger.info("Network movement refresh already running tenant=%s — skipped", tenant_id)
        return {"tenant_id": tenant_id, "skipped": True, "reason": "already_running"}
    try:
        return _refresh_network_movement(tenant_id)
    finally:
        lock.release()


def _refresh_network_movement(tenant_id: str) -> dict:
    stores = repo.list_active_stores(tenant_id)
    store_ids = [s["store_id"] for s in stores]
    if len(store_ids) < 2:
        # Nothing to compare across — clear any stale rows and stop.
        written = repo.replace_all(tenant_id, [])
        return {"tenant_id": tenant_id, "store_count": len(store_ids),
                "canonical_groups": 0, "rows_written": written}

    rolling_days = repo.latest_rolling_days(tenant_id, store_ids)

    # One bulk query per store (never per product) — reused verbatim.
    metrics_by_store = {
        sid: repo.store_movement_metrics(tenant_id, sid, rolling_days)
        for sid in store_ids
    }

    # Nodes = (store_id, product_code) with real presence: it has sold in the
    # window, or it carries stock right now. A product neither selling nor
    # stocked anywhere contributes nothing to network intelligence.
    nodes = []
    for sid in store_ids:
        for code, m in metrics_by_store[sid].items():
            if (m.get("sales_qty") or 0) > 0 or (m.get("stock") or 0) > 0:
                nodes.append((sid, code))

    mappings = repo.load_mapping_edges(tenant_id, store_ids)
    groups, edge_stats = _group_by_presence(nodes, mappings)
    rows = _build_rows(tenant_id, groups, edge_stats, metrics_by_store, rolling_days)

    written = repo.replace_all(tenant_id, rows)
    persisted_groups = len({row["canonical_product_id"] for row in rows})
    logger.info(
        "Network movement refreshed tenant=%s stores=%s groups=%s rows=%s",
        tenant_id, len(store_ids), persisted_groups, written,
    )
    return {
        "tenant_id": tenant_id, "store_count": len(store_ids),
        "canonical_groups": persisted_groups, "rows_written": written,
        "rolling_days": rolling_days,
    }


# --------------------------------------------------------------------------
# Network Opportunities — reads the persisted cache only (see repo docstring).
# Never recomputes network movement, never touches the VPL/order items, never
# adds a product to procurement eligibility on its own.
# --------------------------------------------------------------------------

def list_network_opportunities(tenant_id: str, store_id: str, refresh_id: str,
                                page: int = 1, page_size: int = 50) -> dict:
    """Products this store's own catalogue shows as NONMOVING (zero recent
    local sales) but the network cache shows as genuinely FAST/MEDIUM
    elsewhere, and that are not already on this store's live VPL. Scope note:
    a product the store's own system has NO record of at all (never stocked,
    never sold — no row to classify) is out of scope here; this covers
    products present locally with zero recent sales, matching the worked
    example (local stock > 0, local sales = 0)."""
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    items = repo.list_opportunities(tenant_id, store_id, refresh_id, page, page_size)
    total = repo.count_opportunities(tenant_id, store_id, refresh_id)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
