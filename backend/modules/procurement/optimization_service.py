"""Supplier Order Optimization Engine.

The final optimization stage before Export. After Auto Supplier Assignment some
suppliers sit below their Minimum Order Value and cannot be exported. This engine
suggests moving the *smallest additional purchase value* of products from other
suppliers (who also supply them) into each below-minimum supplier so it reaches
its minimum, while never dropping a donor supplier below its own minimum.

Design
------
* Runs entirely in memory over batched loads (Performance §11): draft
  assignments, min-order config, per-item candidate suppliers (reusing the
  existing supplier-recommendation query) and, when enabled, live stock.
* Value basis = Final-Qty × PTR (Last Purchase Rate → VPL PTR cost), the same
  basis the Supplier Queue shows, so the money numbers agree across panels.
* Product selection is an exact subset-sum: the combination with the lowest
  total added value ≥ the gap, tie-broken by fewest products, then by the
  candidate preference order (live stock, recent history, better cost, §4).
* Moves are only *suggested* here; applying a move reuses the existing
  assignment supplier-change path and writes an audit row (§12).
"""

import logging
import math

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import optimization_repository as repo
from modules.procurement import assignment_repository as assign_repo
from modules.procurement import supplier_repository as supplier_repo

logger = logging.getLogger("procurement.optimization")

_EPS = 1e-6


# --------------------------------------------------------------------------
# Subset-sum: smallest total value ≥ gap, then fewest items
# --------------------------------------------------------------------------

def _best_combo(cands, gap):
    """Return the indices (into ``cands``) of the lowest-total combination whose
    summed value reaches ``gap``, tie-broken by fewest items then by candidate
    order (earlier = more preferred). Returns None if unreachable, [] if gap<=0.

    Values are rounded to whole rupees for a bounded DP; the ceiling never
    exceeds ~2×gap because any single candidate ≥ gap is handled separately as a
    one-item option (a bigger single item can never beat it on total)."""
    if gap <= _EPS:
        return []
    n = len(cands)
    vals = [max(1, int(round(c["value"]))) for c in cands]
    G = max(1, int(math.ceil(gap - _EPS)))

    # Best single item that alone clears the gap (fewest rupees over).
    solo = None  # (total, idx)
    for i, v in enumerate(vals):
        if v >= G and (solo is None or v < solo[0]):
            solo = (v, i)

    # Multi-item combinations drawn from items smaller than the gap.
    small = [i for i in range(n) if vals[i] < G]
    combo = None  # (total, count, [idx])
    if small:
        ceiling = G + max(vals[i] for i in small)
        dp = [None] * (ceiling + 1)
        dp[0] = (0, ())
        for i in small:
            v = vals[i]
            for s in range(ceiling, v - 1, -1):
                prev = dp[s - v]
                if prev is not None:
                    cand = (prev[0] + 1, prev[1] + (i,))
                    if dp[s] is None or cand < dp[s]:
                        dp[s] = cand
        for s in range(G, ceiling + 1):
            if dp[s] is not None:
                combo = (s, dp[s][0], list(dp[s][1]))
                break

    options = []
    if solo is not None:
        options.append((solo[0], 1, [solo[1]]))
    if combo is not None:
        options.append((combo[0], combo[1], combo[2]))
    if not options:
        return None
    options.sort(key=lambda o: (o[0], o[1]))  # §4: lowest value, then fewest items
    return options[0][2]


def _optimize_one(gap, cands, slack_by_source):
    """Pick a combo for one below-minimum supplier that also keeps every donor
    above its own minimum (per-source cumulative ≤ that source's slack). Drops
    the least-preferred offending candidate and retries if a combo would push a
    donor under; returns the chosen candidate dicts or None."""
    pool = [c for c in cands if c["value"] > _EPS
            and c["value"] <= slack_by_source.get(c["source"], 0) + _EPS]
    banned = set()
    for _ in range(len(pool) + 1):
        active = [c for i, c in enumerate(pool) if i not in banned]
        idxs = _best_combo(active, gap)
        if not idxs:
            return None
        chosen = [active[i] for i in idxs]
        by_src = {}
        for c in chosen:
            by_src[c["source"]] = by_src.get(c["source"], 0) + c["value"]
        violating = {s for s, v in by_src.items() if v > slack_by_source.get(s, 0) + _EPS}
        if not violating:
            return chosen
        # Ban the least-preferred chosen candidate from a violating source.
        drop = next((c for c in reversed(chosen) if c["source"] in violating), None)
        if drop is None:
            return None
        banned.add(pool.index(drop))
    return None


# --------------------------------------------------------------------------
# Analysis (suggest only — no writes)
# --------------------------------------------------------------------------

def _move_dto(c, to_supplier):
    return {
        "assignment_id": c["assignment_id"],
        "order_item_id": c["order_item_id"],
        "product_code": c["product_code"],
        "product_name": c["product_name"],
        "from_supplier": c["source"],
        "to_supplier": to_supplier,
        "qty": c["qty"],
        "value": round(c["value"], 2),
    }


def analyze(tenant_id, refresh_id, price_tolerance=0.10, use_live_stock=True):
    repo.ensure_schema()
    assignments = repo.load_draft_assignments(tenant_id, refresh_id)

    store_id = next((a["store_id"] for a in assignments if a.get("store_id")), None)
    min_orders = repo.list_min_orders(tenant_id, store_id) if store_id else {}
    # A supplier only participates in Optimization when explicitly opted in —
    # a configured min_order_value alone is no longer enough (§10/§11).
    consider = repo.list_consider_flags(tenant_id, store_id) if store_id else {}

    def _effective_min(code):
        return min_orders.get(code, 0) if consider.get(code) else 0

    # Candidate suppliers (who supplies each product + their last rate / history)
    # — one batched round-trip, reusing the supplier-recommendation query.
    cand_rows = supplier_repo.top_suppliers_bulk(tenant_id, refresh_id, 50)
    cand_by_item = {}
    for r in cand_rows:
        oid = str(r["order_item_id"])
        cand_by_item.setdefault(oid, {})[str(r["supplier_code"])] = {
            "rate": float(r["last_purchase_rate"]) if r.get("last_purchase_rate") is not None else None,
            "freq": int(r.get("purchase_frequency") or 0),
        }

    live_stock = repo.load_live_stock_map(tenant_id, refresh_id, store_id) if use_live_stock else {}
    # A supplier has live-stock data at all only if it appears in the map.
    stocked_suppliers = {s for (s, _p) in live_stock}

    # Current draft value / qty / products per supplier.
    value_by = {}
    qty_by = {}
    count_by = {}
    for a in assignments:
        s = a["supplier_code"]
        value_by[s] = value_by.get(s, 0) + a["assigned_qty"] * a["ptr"]
        qty_by[s] = qty_by.get(s, 0) + a["assigned_qty"]
        count_by[s] = count_by.get(s, 0) + 1
    original_value = dict(value_by)

    def _movable_for(dest):
        """Candidate assignments movable into ``dest`` (all §2 rules applied)."""
        out = []
        for a in assignments:
            src = a["supplier_code"]
            if src == dest or a["assignment_id"] in reserved:
                continue
            oid = a["order_item_id"]
            dest_cand = cand_by_item.get(oid, {}).get(dest)
            if dest_cand is None:
                continue  # destination does not supply this product
            value = a["assigned_qty"] * a["ptr"]
            if value <= _EPS:
                continue
            # Live stock: never suggest a product a stocked destination has 0 of.
            if dest in stocked_suppliers and live_stock.get((dest, a["product_code"]), 0) <= 0:
                continue
            # Purchase-price tolerance between source and destination last rates.
            dest_rate = dest_cand.get("rate")
            src_rate = cand_by_item.get(oid, {}).get(src, {}).get("rate")
            if dest_rate is not None and src_rate not in (None, 0):
                if abs(dest_rate - src_rate) / src_rate > price_tolerance:
                    continue
            out.append({
                "assignment_id": a["assignment_id"],
                "order_item_id": oid,
                "product_code": a["product_code"],
                "product_name": a["product_name"],
                "source": src,
                "qty": a["assigned_qty"],
                "value": value,
                "dest_rate": dest_rate,
                "src_rate": src_rate,
                "has_stock": dest in stocked_suppliers
                             and live_stock.get((dest, a["product_code"]), 0) > 0,
                "freq": dest_cand.get("freq", 0),
            })
        # Preference order (§4 items 3-6) so ties in the DP pick the better one:
        # live stock, then recent/frequent history, then better (lower) cost.
        out.sort(key=lambda c: (0 if c["has_stock"] else 1, -c["freq"],
                                c["dest_rate"] if c["dest_rate"] is not None else 1e18))
        return out

    reserved = set()
    suggestions_by = {}  # dest -> [chosen candidate dicts]
    movable_by = {}      # dest -> [movable candidate dicts] (for Manual Move)

    below = [s for s, v in value_by.items() if _effective_min(s) > 0 and v < _effective_min(s) - _EPS]
    # Easiest wins first (smallest gap) so scarce donations satisfy the most suppliers.
    below.sort(key=lambda s: _effective_min(s) - value_by[s])
    for dest in below:
        gap = _effective_min(dest) - value_by[dest]
        if gap <= _EPS:
            continue
        slack_by_source = {s: value_by[s] - _effective_min(s) for s in value_by}
        movable = _movable_for(dest)
        movable_by[dest] = movable
        chosen = _optimize_one(gap, movable, slack_by_source)
        if not chosen:
            suggestions_by[dest] = []
            continue
        for c in chosen:
            reserved.add(c["assignment_id"])
            value_by[c["source"]] -= c["value"]
            qty_by[c["source"]] -= c["qty"]
            count_by[c["source"]] -= 1
            value_by[dest] += c["value"]
            qty_by[dest] += c["qty"]
            count_by[dest] += 1
        suggestions_by[dest] = chosen

    suppliers = []
    for s in sorted(original_value, key=lambda x: -original_value[x]):
        mn = _effective_min(s)
        cur = original_value[s]
        proj = value_by[s]
        sugg = suggestions_by.get(s, None)
        if mn <= 0 or cur >= mn - _EPS:
            status = "ok"
        elif sugg:
            status = "ready" if proj >= mn - _EPS else "short"
        else:
            status = "no_solution"
        suppliers.append({
            "supplier_code": s,
            "min_value": mn,
            "current_value": round(cur, 2),
            "gap": round(max(0.0, mn - cur), 2),
            "projected_value": round(proj, 2),
            "current_products": count_by.get(s, 0),
            "status": status,
            "suggestions": [_move_dto(c, s) for c in (sugg or [])],
            # The full movable pool for a below-minimum supplier powers Manual Move
            # (§8) in the UI; suppliers already at/above minimum need none.
            "movable": [_move_dto(c, s) for c in movable_by.get(s, [])] if status != "ok" else [],
        })

    return {
        "refresh_id": refresh_id,
        "store_id": store_id,
        "price_tolerance": price_tolerance,
        "use_live_stock": bool(use_live_stock and live_stock),
        "below_minimum": len(below),
        "suppliers": suppliers,
    }


# --------------------------------------------------------------------------
# Apply moves (Accept / Accept All / Manual Move) — reuses the assignment
# supplier-change path and writes one audit row per move.
# --------------------------------------------------------------------------

def _move_one(conn, tenant_id, refresh_id, assignment_id, to_supplier, reason,
              moved_by, validate_supplies):
    a = repo.get_assignment_row(conn, tenant_id, assignment_id)
    if not a:
        raise ValueError("assignment not found")
    if a["assignment_status"] == "exported":
        raise ValueError("assignment already exported")
    from_supplier = a["supplier_code"]
    if from_supplier == to_supplier:
        raise ValueError("already assigned to this supplier")
    if validate_supplies and not repo.supplies_product(
        tenant_id, a["store_id"], a["product_code"], to_supplier
    ):
        raise ValueError("destination supplier does not supply this product")
    if assign_repo.duplicate_active_exists(
        conn, tenant_id, a["order_item_id"], to_supplier,
        exclude_assignment_id=assignment_id,
    ):
        raise ValueError("destination already has an active assignment for this item")

    assign_repo.update_supplier(conn, tenant_id, assignment_id, to_supplier, moved_by)
    ptr_qty = float(a["assigned_qty"] or 0)
    repo.insert_move(
        conn, tenant_id=tenant_id, cycle_id=a["cycle_id"], refresh_id=refresh_id,
        store_id=a["store_id"], order_item_id=a["order_item_id"],
        assignment_id=assignment_id, product_code=a["product_code"],
        from_supplier=from_supplier, to_supplier=to_supplier,
        moved_qty=ptr_qty, moved_value=None, reason=reason, moved_by=moved_by,
    )
    return {"assignment_id": assignment_id, "from_supplier": from_supplier,
            "to_supplier": to_supplier, "status": "moved"}


def apply_moves(tenant_id, refresh_id, moves, applied_by, reason="auto"):
    """Apply a batch of suggested moves (Accept / Accept All). Each move is
    validated independently; a bad line is reported, not fatal."""
    repo.ensure_schema()
    if not moves:
        raise HTTPException(status_code=400, detail="No moves to apply")
    results = []
    conn = get_connection()
    try:
        for m in moves:
            aid = m.get("assignment_id")
            try:
                results.append(_move_one(
                    conn, tenant_id, refresh_id, aid, m.get("to_supplier"),
                    reason, applied_by, validate_supplies=True,
                ))
            except ValueError as exc:
                results.append({"assignment_id": aid, "status": "skipped",
                                "reason": str(exc)})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    moved = sum(1 for r in results if r["status"] == "moved")
    logger.info("Optimization apply tenant=%s refresh=%s moved=%s skipped=%s reason=%s by=%s",
                tenant_id, refresh_id, moved, len(results) - moved, reason, applied_by)
    return {"moved": moved, "skipped": len(results) - moved, "results": results}


def manual_move(tenant_id, refresh_id, assignment_id, to_supplier, moved_by):
    """Purchase manager moves one product to another supplier (§8). The
    destination must sell the product; totals/export-readiness recompute on the
    client from the reloaded queue."""
    repo.ensure_schema()
    if not to_supplier or not str(to_supplier).strip():
        raise HTTPException(status_code=400, detail="to_supplier is required")
    conn = get_connection()
    try:
        try:
            res = _move_one(conn, tenant_id, refresh_id, assignment_id,
                            to_supplier, "manual", moved_by, validate_supplies=True)
        except ValueError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail=str(exc))
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info("Manual move tenant=%s refresh=%s assignment=%s -> %s by=%s",
                tenant_id, refresh_id, assignment_id, to_supplier, moved_by)
    return res


def audit(tenant_id, refresh_id):
    return {"moves": repo.list_moves(tenant_id, refresh_id)}


# --------------------------------------------------------------------------
# Minimum Order Value config
# --------------------------------------------------------------------------

def list_min_orders(tenant_id, store_id):
    return {"min_orders": repo.list_min_orders(tenant_id, store_id)}


def set_min_order(tenant_id, store_id, supplier_code, min_order_value, updated_by):
    if min_order_value is None or min_order_value < 0:
        raise HTTPException(status_code=400, detail="min_order_value cannot be negative")
    repo.upsert_min_order(tenant_id, store_id, supplier_code, min_order_value, updated_by)
    return {"supplier_code": supplier_code, "store_id": store_id,
            "min_order_value": min_order_value}


def list_min_order_config(tenant_id, store_id):
    return {"config": repo.list_min_order_config(tenant_id, store_id)}


def set_consider_minimum_order(tenant_id, store_id, supplier_code, consider_minimum_order, updated_by):
    repo.upsert_consider_flag(tenant_id, store_id, supplier_code, bool(consider_minimum_order), updated_by)
    return {"supplier_code": supplier_code, "store_id": store_id,
            "consider_minimum_order": bool(consider_minimum_order)}
