"""Rate Analysis — supplier purchase-rate tools for the Stock Client.

Four read-only analyses, each returned as the uniform
``{title, notes, sheets: [{name, columns, rows}]}`` result that the client
renders in one grid and ``excel.build_workbook`` exports as-is:

  * quote_compare   — a supplier's quoted PTR list vs what every store last paid,
                      the chain lowest/average, and a 1-month order in strips
                      (sales / sales_days x order_days, stock NOT deducted —
                      owner ruling 2026-10-30).
  * fast_movers     — fast-moving products of chosen suppliers, with the LEAST
                      rate every supplier billed in the last ``rate_days``.
  * rate_difference — every bill line vs the chain least rate for the same
                      product, pack and month (extra paid / "to verify").
  * suppliers / quote_match — pickers for the above.

Conventions (agreed while doing these by hand, 2026-10-30/31):
  * Rates are PTR before GST. Net rate = PTR x (1 - disc%) x qty / (qty + free):
    free goods count ONCE (the first hand-made report applied them twice).
  * Product codes are store-local, so products are matched across stores by a
    normalised name (``norm_key``).
  * A rate more than 20% below the usual (median) rate of the same product is
    treated as a probable entry error (e.g. a 15's pack billed at the old 10's
    rate) and never becomes "best"/"least".
  * Bills between the tenant's own stores (supplier name starting with the
    common prefix of the store names, e.g. "NATHAN MEDICALS") are not suppliers.
"""

import math
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from modules.rate_analysis import repository as repo

ENTRY_ERROR_RATIO = 0.8
_FORM_WORDS = re.compile(r"\b(TABLETS?|TABS?|CAPSULES?|CAPS?|SYRUP|SYP|SYR)\b")
_SURGICAL = re.compile(r"SYRINGE|NEEDLE|PLASTER|GLOVE|BANDAGE|BAND AID|EAR PLUG|MICROPORE|TULLE|BLADE|LANCET|COTTON|GAUZE|"
                       r"MASK|CATHETER|\bI\.?V\b|IV SET|WATER FOR INJ|FIRST AID|CREPE|URINE BAG|DRESSING|SURGICAL")
_STOP = {"TAB", "TABS", "TABLET", "TABLETS", "CAP", "CAPS", "CAPSULE", "CAPSULES", "SYP", "SYR", "SYRUP", "THE", "AND"}


# ---------------------------------------------------------------- helpers
def norm_key(name):
    s = _FORM_WORDS.sub(" ", (name or "").upper())
    s = re.sub(r"\b10'?S\b", " ", s)
    return re.sub(r"[^A-Z0-9]", "", s).replace("MG", "")


def net_rate(ptr, disc, qty, free):
    qty = float(qty or 0)
    free = float(free or 0)
    base = float(ptr or 0) * (1 - float(disc or 0) / 100)
    return base * qty / (qty + free) if qty > 0 else base


def _skey(gst, name):
    gst = (gst or "").strip().upper()
    return gst if len(gst) == 15 else "N:" + re.sub(r"\s+", " ", (name or "").upper()).strip()


def _internal_prefix(stores):
    words = [s["store_name"].upper().split() for s in stores if s.get("store_name")]
    if not words:
        return ""
    common = []
    for parts in zip(*words):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    return " ".join(common)


def _day(d):
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _dt(d):
    return datetime.combine(_day(d), datetime.min.time())


def _median_guard(values):
    return statistics.median(values) * ENTRY_ERROR_RATIO if values else 0


def _col(key, label, fmt="text", group=None, width=None):
    c = {"key": key, "label": label, "format": fmt}
    if group:
        c["group"] = group
    if width:
        c["width"] = width
    return c


def _r2(v):
    return None if v is None else round(float(v), 2)


class _Ctx:
    """Stores, code maps and enriched purchase lines for one tenant."""

    def __init__(self, tenant_id):
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        self.tenant_id = tenant_id
        self.stores = repo.tenant_stores(tenant_id)
        if not self.stores:
            raise HTTPException(status_code=404, detail="No active stores for this tenant")
        self.store_ids = [s["store_id"] for s in self.stores]
        self.code = {s["store_id"].upper(): s["store_code"] for s in self.stores}
        self.codes = [s["store_code"] for s in self.stores]
        self.prefix = _internal_prefix(self.stores)
        self._sup_names = defaultdict(lambda: defaultdict(int))

    def is_internal(self, name):
        return bool(self.prefix) and (name or "").upper().startswith(self.prefix)

    def lines(self, date_from, date_to, codes=None):
        out = []
        for r in repo.purchase_lines(self.tenant_id, self.store_ids, _dt(date_from), _dt(date_to), codes):
            r["store"] = self.code.get(r["store_id"].upper(), "?")
            r["key"] = norm_key(r["product_name"])
            r["skey"] = _skey(r["gst"], r["supplier_name"])
            r["internal"] = self.is_internal(r["supplier_name"])
            r["net"] = net_rate(r["ptr"], r["disc_pct"], r["qty"], r["free_qty"])
            r["date"] = _day(r["grn_date"])
            r["sale_unit"] = float(r["sale_unit"] or 1) or 1.0
            self._sup_names[r["skey"]][(r["supplier_name"] or "").upper()] += 1
            out.append(r)
        return out

    def sup_name(self, skey):
        names = self._sup_names.get(skey)
        return max(names, key=names.get) if names else skey

    def products(self):
        rows = repo.all_products(self.tenant_id, self.store_ids)
        for r in rows:
            r["store"] = self.code.get(r["store_id"].upper(), "?")
            r["key"] = norm_key(r["product_name"])
            r["sale_unit"] = float(r["sale_unit"] or 1) or 1.0
        return rows


def _sales_strips(ctx, prows, date_from, date_to):
    """{key: {store_code: strips}} for the given product rows."""
    qty = repo.sales_qty([(p["store_id"], p["product_code"]) for p in prows], _dt(date_from), _dt(date_to))
    out = defaultdict(lambda: defaultdict(float))
    for p in prows:
        q = qty.get((p["store_id"].upper(), int(p["product_code"])))
        if q:
            out[p["key"]][p["store"]] += q / p["sale_unit"]
    return out


# ---------------------------------------------------------------- pickers
def suppliers(tenant_id, days=90):
    ctx = _Ctx(tenant_id)
    end = date.today() + timedelta(days=1)
    agg = {}
    for r in ctx.lines(end - timedelta(days=days), end):
        if r["internal"]:
            continue
        a = agg.setdefault(r["skey"], {"key": r["skey"], "gst": r["gst"] if len(r["gst"]) == 15 else "",
                                       "stores": set(), "bills": set(), "value": 0.0})
        a["stores"].add(r["store"])
        a["bills"].add((r["store"], r["grn_no"]))
        a["value"] += float(r["ptr"]) * (1 - float(r["disc_pct"]) / 100) * float(r["qty"])
    out = [{"key": a["key"], "name": ctx.sup_name(a["key"]), "gst": a["gst"], "stores": sorted(a["stores"]),
            "bills": len(a["bills"]), "value": round(a["value"])} for a in agg.values()]
    out.sort(key=lambda x: -x["value"])
    return {"days": days, "stores": ctx.codes, "suppliers": out}


def _tokens(text):
    return [t for t in re.findall(r"[A-Z0-9]+", (text or "").upper()) if t not in _STOP]


def quote_match(tenant_id, lines):
    """Candidate products (grouped by normalised name) for each quoted line."""
    ctx = _Ctx(tenant_id)
    groups = {}
    for p in ctx.products():
        g = groups.setdefault(p["key"], {"key": p["key"], "names": set(), "stores": set(), "mrp": 0.0, "packs": set()})
        g["names"].add(p["product_name"])
        g["stores"].add(p["store"])
        g["mrp"] = max(g["mrp"], float(p["mrp"] or 0))
        g["packs"].add(int(p["sale_unit"]))
    by_first = defaultdict(list)
    for g in groups.values():
        g["tokens"] = set(_tokens(" ".join(g["names"])))
        first = _tokens(min(g["names"], key=len))[:1]
        if first:
            by_first[first[0][:3]].append(g)

    results = []
    for ln in lines:
        qt = _tokens(ln.get("text"))
        cands = []
        if qt:
            brand = qt[0]
            for g in by_first.get(brand[:3], []):
                gtok = g["tokens"]
                if not any(t.startswith(brand) or brand.startswith(t) for t in gtok if len(t) >= 3):
                    continue
                hit = sum(1 for t in qt if t in gtok or any(len(t) >= 3 and x.startswith(t) for x in gtok))
                score = hit / len(qt) - 0.02 * max(0, len(gtok) - len(qt))
                mrp = float(ln.get("mrp") or 0)
                if mrp and g["mrp"]:
                    score += 0.3 * (1 - min(1.0, abs(g["mrp"] - mrp) / mrp))
                score += 0.03 * len(g["stores"])
                cands.append((score, g))
        cands.sort(key=lambda x: -x[0])
        results.append({"text": ln.get("text"), "candidates": [
            {"key": g["key"], "label": min(g["names"], key=len), "names": sorted(g["names"]), "stores": sorted(g["stores"]),
             "mrp": _r2(g["mrp"]), "packs": "/".join(map(str, sorted(g["packs"]))), "score": round(s, 3)}
            for s, g in cands[:8]]})
    return {"lines": results}


# ---------------------------------------------------------------- quote compare
def quote_compare(tenant_id, lines, compare_days=90, sales_days=90, order_days=30):
    ctx = _Ctx(tenant_id)
    lines = [ln for ln in lines if ln.get("key")]
    if not lines:
        raise HTTPException(status_code=400, detail="Match at least one quoted product first")
    end = date.today() + timedelta(days=1)
    c_from, s_from = end - timedelta(days=compare_days), end - timedelta(days=sales_days)
    keys = {ln["key"] for ln in lines}
    prows = [p for p in ctx.products() if p["key"] in keys]
    by_key = defaultdict(list)
    for p in prows:
        by_key[p["key"]].append(p)
    sales = _sales_strips(ctx, prows, s_from, end)
    bills = defaultdict(list)
    for r in ctx.lines(c_from, end, [(p["store_id"], p["product_code"]) for p in prows]):
        if not r["internal"]:
            bills[r["key"]].append(r)
    S = ctx.codes

    cols = [_col("no", "#", "int"), _col("product", "Product (quote)", width=24), _col("matched", "Matched as", width=24),
            _col("pack", "Pack"), _col("q_mrp", "Quote MRP", "money"), _col("q_ptr", "Quote PTR", "money")]
    cols += [_col(f"last_{s}", s, "money", "Last PTR per store") for s in S]
    cols += [_col("low", "Lowest PTR", "money", f"Chain, last {compare_days} days"),
             _col("low_at", "Lowest at (store / supplier / date)", group=f"Chain, last {compare_days} days", width=36),
             _col("avg", "Avg PTR", "money", f"Chain, last {compare_days} days"),
             _col("d_low", "Quote - lowest", "money", "Quote vs chain"), _col("d_avg", "Quote - avg", "money", "Quote vs chain"),
             _col("saving", f"Saving at quote ({compare_days}D)", "int", "Quote vs chain"),
             _col("verdict", "Verdict", group="Quote vs chain", width=18)]
    cols += [_col(f"ord_{s}", s, "int", f"Order (strips) = {sales_days}D sales / {sales_days} x {order_days}") for s in S]
    cols += [_col("ord_total", "Total strips", "int", "Order"), _col("ord_value", "Value at quote", "int", "Order")]

    detail_cols = [_col("no", "#", "int"), _col("product", "Product (quote)", width=24), _col("store", "Store"),
                   _col("names", "Store product", width=30), _col("pack", "Pack", "int"),
                   _col("last_date", "Last bill", "date"), _col("last_sup", "Last supplier", width=28), _col("last_grn", "Bill no"),
                   _col("last_mrp", "MRP", "money"), _col("last_qty", "Qty", "int"), _col("last_free", "Free", "int"),
                   _col("last_ptr", "PTR", "money"), _col("last_disc", "Disc %", "money"), _col("last_net", "Net rate", "money"),
                   _col("d_quote", "PTR - quote", "money"), _col("avg_ptr", f"Avg PTR {compare_days}D", "money"),
                   _col("min_ptr", f"Min PTR {compare_days}D", "money"),
                   _col("sales", f"Sales {sales_days}D (strips)", "num1"), _col("order", "Order (strips)", "int")]

    rows, detail = [], []
    tot_value = 0
    for i, ln in enumerate(lines, 1):
        q = float(ln.get("ptr") or 0) or None
        B = bills.get(ln["key"], [])
        guard = _median_guard([b["ptr"] for b in B])
        ok = [b for b in B if b["ptr"] >= guard]
        lp = min(ok, key=lambda b: (b["ptr"], b["date"])) if ok else None
        units = sum(float(b["qty"]) for b in ok)
        avg = sum(b["ptr"] * float(b["qty"]) for b in ok) / units if units else None
        P = by_key.get(ln["key"], [])
        packs = sorted({int(p["sale_unit"]) for p in P})
        row = {"no": i, "product": ln.get("label") or ln.get("text"), "matched": min((p["product_name"] for p in P), key=len, default=""),
               "pack": "/".join(map(str, packs)), "q_mrp": _r2(ln.get("mrp")), "q_ptr": _r2(q), "_flags": {}}
        for s in S:
            sb = sorted([b for b in B if b["store"] == s], key=lambda b: (b["date"], b["grn_no"]))
            row[f"last_{s}"] = _r2(sb[-1]["ptr"]) if sb else None
            if sb and q:
                row["_flags"][f"last_{s}"] = "bad" if sb[-1]["ptr"] > q + 0.005 else ("good" if sb[-1]["ptr"] < q - 0.005 else None)
        if lp:
            row.update(low=_r2(lp["ptr"]), low_at=f"{lp['store']} / {ctx.sup_name(lp['skey'])} / {lp['date']:%d-%m-%Y}", avg=_r2(avg))
        if q and lp:
            saving = sum((b["ptr"] - q) * float(b["qty"]) for b in ok)
            row.update(d_low=_r2(q - lp["ptr"]), d_avg=_r2(q - avg) if avg else None, saving=round(saving))
            verdict = ("QUOTE CHEAPEST" if q < lp["ptr"] - 0.005 else "BELOW OUR AVG" if avg and q < avg - 0.005
                       else "SAME" if avg and abs(q - avg) <= 0.005 else "QUOTE COSTLIER")
            row["verdict"] = verdict
            row["_flags"]["verdict"] = "good" if verdict in ("QUOTE CHEAPEST", "BELOW OUR AVG") else "bad" if verdict == "QUOTE COSTLIER" else "warn"
        elif not B:
            row["verdict"] = "NOT BOUGHT"
            row["_flags"]["verdict"] = "warn"
        total = 0
        for s in S:
            strips = sales.get(ln["key"], {}).get(s, 0.0)
            has = any(p["store"] == s for p in P)
            o = math.ceil(round(strips / sales_days * order_days, 4)) if strips > 0 else 0
            row[f"ord_{s}"] = o if has else None
            if o:
                row["_flags"][f"ord_{s}"] = "good"
            total += o
            if has:
                sb = sorted([b for b in B if b["store"] == s], key=lambda b: (b["date"], b["grn_no"]))
                so = [b for b in sb if b["ptr"] >= guard]
                su = sum(float(b["qty"]) for b in so)
                last = sb[-1] if sb else None
                d = {"no": i, "product": row["product"], "store": s,
                     "names": "; ".join(sorted({p["product_name"] for p in P if p["store"] == s})),
                     "pack": max((p["sale_unit"] for p in P if p["store"] == s), default=1),
                     "sales": round(strips, 1), "order": o, "_flags": {}}
                if last:
                    d.update(last_date=last["date"], last_sup=ctx.sup_name(last["skey"]), last_grn=last["grn_no"],
                             last_mrp=_r2(last["mrp"]), last_qty=last["qty"], last_free=last["free_qty"], last_ptr=_r2(last["ptr"]),
                             last_disc=_r2(last["disc_pct"]), last_net=_r2(last["net"]),
                             d_quote=_r2(last["ptr"] - q) if q else None,
                             avg_ptr=_r2(sum(b["ptr"] * float(b["qty"]) for b in so) / su) if su else None,
                             min_ptr=_r2(min((b["ptr"] for b in so), default=None)))
                    if q:
                        d["_flags"]["d_quote"] = "bad" if last["ptr"] > q + 0.005 else ("good" if last["ptr"] < q - 0.005 else None)
                detail.append(d)
        row["ord_total"] = total
        row["ord_value"] = round(total * q) if q else None
        tot_value += row["ord_value"] or 0
        rows.append(row)
    total_row = {"product": "TOTAL", "_total": True, "ord_total": sum(r["ord_total"] for r in rows), "ord_value": tot_value,
                 "saving": sum(r.get("saving") or 0 for r in rows)}
    for s in S:
        total_row[f"ord_{s}"] = sum(r.get(f"ord_{s}") or 0 for r in rows)
    rows.append(total_row)
    return {
        "title": "Quote vs store purchase rate + 1-month order",
        "notes": [f"Store PTR = supplier bills (IV) of the last {compare_days} days, PTR before discount/free/GST. "
                  f"Rates >20% below the usual rate are ignored as entry errors; own-store bills excluded.",
                  f"Order (strips) = sales of the last {sales_days} days / {sales_days} x {order_days}, rounded up, "
                  "stock NOT deducted. Strip = SaleUnit (packing per strip). Value = total strips x quote PTR."],
        "sheets": [{"name": "Quote Compare", "columns": cols, "rows": rows},
                   {"name": "Store-wise Detail", "columns": detail_cols, "rows": detail}],
    }


# ---------------------------------------------------------------- fast movers
def fast_movers(tenant_id, supplier_keys, sales_days=90, rate_days=30, min_stores=3, exclude_keys=None):
    ctx = _Ctx(tenant_id)
    chosen = set(supplier_keys or [])
    if not chosen:
        raise HTTPException(status_code=400, detail="Choose at least one supplier")
    exclude = {norm_key(k) for k in (exclude_keys or [])}
    end = date.today() + timedelta(days=1)
    s_from, r_from = end - timedelta(days=sales_days), end - timedelta(days=rate_days)
    L = ctx.lines(min(s_from, r_from), end)
    universe = {r["key"] for r in L if r["skey"] in chosen and r["date"] >= s_from and r["key"] not in exclude}
    prows = [p for p in ctx.products() if p["key"] in universe]
    names, packs = defaultdict(set), defaultdict(set)
    for p in prows:
        names[p["key"]].add(p["product_name"])
        packs[p["key"]].add(int(p["sale_unit"]))
    sales = _sales_strips(ctx, prows, s_from, end)
    rate_lines = defaultdict(list)
    for r in L:
        if r["key"] in universe and r["date"] >= r_from and not r["internal"]:
            rate_lines[r["key"]].append(r)
    S = ctx.codes
    chosen_names = sorted(ctx.sup_name(k) for k in chosen)

    items = []
    for k in universe:
        st = sales.get(k, {})
        sold_in = sum(1 for v in st.values() if v > 0)
        if sold_in < min_stores:
            continue
        R = rate_lines.get(k, [])
        guard = _median_guard([b["ptr"] for b in R])
        bysup = defaultdict(list)
        for b in R:
            if b["ptr"] >= guard:
                bysup[b["skey"]].append(b)
        sups = []
        for sk, X in bysup.items():
            lo = min(X, key=lambda b: (b["ptr"], b["date"]))
            la = max(X, key=lambda b: (b["date"], b["grn_no"]))
            sups.append({"skey": sk, "name": ctx.sup_name(sk), "mine": sk in chosen, "lo": lo, "last": la})
        sups.sort(key=lambda x: x["lo"]["ptr"])
        name = min(names[k], key=len)
        items.append({"key": k, "name": name, "cat": "Surgical" if _SURGICAL.search(name) else "Medicine",
                      "names": sorted(names[k]), "packs": "/".join(map(str, sorted(packs[k]))),
                      "month": sum(st.values()) / sales_days * 30, "per": st, "sups": sups})
    items.sort(key=lambda x: (x["cat"] != "Medicine", -x["month"]))

    G1, G2, G3, G4 = (f"Strips / month (last {sales_days} days sales)", f"LEAST RATE - all suppliers, last {rate_days} days",
                      "Chosen suppliers - least", "Other suppliers - least")
    cols = [_col("no", "#", "int"), _col("cat", "Category"), _col("product", "Product", width=28), _col("pack", "Pack"),
            _col("month", "Chain", "int", G1)] + [_col(f"m_{s}", s, "int", G1) for s in S]
    cols += [_col("l_ptr", "Least PTR", "money", G2), _col("l_sup", "Supplier", group=G2, width=26), _col("l_store", "Store", group=G2),
             _col("l_grn", "Bill no", group=G2), _col("l_date", "Received", "date", G2), _col("l_mrp", "MRP", "money", G2),
             _col("l_disc", "Disc %", "money", G2), _col("l_free", "Free", "int", G2), _col("l_net", "Net rate", "money", G2),
             _col("c_ptr", "PTR", "money", G3), _col("c_sup", "Supplier", group=G3, width=22),
             _col("o_ptr", "PTR", "money", G4), _col("o_sup", "Supplier", group=G4, width=22),
             _col("o_diff", "Cheaper by (Rs)", "money", G4),
             _col("value", "Monthly value at least rate", "int"), _col("all", f"All suppliers - least PTR in {rate_days} days", width=80),
             _col("names", "Store product names", width=45)]
    rows = []
    for i, it in enumerate(items, 1):
        sups = it["sups"]
        best = sups[0] if sups else None
        mine = next((x for x in sups if x["mine"]), None)
        other = next((x for x in sups if not x["mine"]), None)
        row = {"no": i, "cat": it["cat"], "product": it["name"], "pack": it["packs"], "month": round(it["month"]),
               "names": " | ".join(it["names"]), "_flags": {}}
        for s in S:
            row[f"m_{s}"] = round(it["per"].get(s, 0) / sales_days * 30)
        if best:
            lo = best["lo"]
            row.update(l_ptr=_r2(lo["ptr"]), l_sup=best["name"], l_store=lo["store"], l_grn=lo["grn_no"], l_date=lo["date"],
                       l_mrp=_r2(lo["mrp"]), l_disc=_r2(lo["disc_pct"]), l_free=lo["free_qty"], l_net=_r2(lo["net"]),
                       value=round(it["month"] * lo["ptr"]))
            row["_flags"]["l_ptr"] = "good"
        else:
            row["l_ptr"] = None
            row["l_sup"] = f"no bill in {rate_days}D"
            row["_flags"]["l_sup"] = "warn"
        if mine:
            row.update(c_ptr=_r2(mine["lo"]["ptr"]), c_sup=mine["name"])
        if other:
            row.update(o_ptr=_r2(other["lo"]["ptr"]), o_sup=other["name"])
            if mine and other["lo"]["ptr"] < mine["lo"]["ptr"] - 0.005:
                row["o_diff"] = _r2(mine["lo"]["ptr"] - other["lo"]["ptr"])
                for c in ("o_ptr", "o_sup", "o_diff"):
                    row["_flags"][c] = "bad"
        row["all"] = "; ".join(f"{x['name']} {x['lo']['ptr']:.2f}" for x in sups)
        rows.append(row)

    scols = [_col("no", "#", "int"), _col("cat", "Category"), _col("product", "Product", width=28), _col("pack", "Pack"),
             _col("month", "Strips / month", "int"), _col("sup", "Supplier", width=30), _col("mine", "Chosen supplier?"),
             _col("rank", "Rank", "int"), _col("ptr", f"Least PTR ({rate_days}D)", "money"), _col("store", "Store"),
             _col("date", "Received", "date"), _col("grn", "Bill no"), _col("mrp", "MRP", "money"), _col("disc", "Disc %", "money"),
             _col("free", "Free", "int"), _col("net", "Net rate", "money"), _col("last", f"Last PTR ({rate_days}D)", "money"),
             _col("last_date", "Last received", "date"), _col("vs", "vs cheapest (Rs)", "money")]
    srows = []
    for i, it in enumerate(items, 1):
        for rk, x in enumerate(it["sups"], 1):
            lo, la = x["lo"], x["last"]
            srows.append({"no": i, "cat": it["cat"], "product": it["name"], "pack": it["packs"], "month": round(it["month"]),
                          "sup": x["name"], "mine": "YES" if x["mine"] else "", "rank": rk, "ptr": _r2(lo["ptr"]),
                          "store": lo["store"], "date": lo["date"], "grn": lo["grn_no"], "mrp": _r2(lo["mrp"]),
                          "disc": _r2(lo["disc_pct"]), "free": lo["free_qty"], "net": _r2(lo["net"]), "last": _r2(la["ptr"]),
                          "last_date": la["date"], "vs": _r2(lo["ptr"] - it["sups"][0]["lo"]["ptr"]),
                          "_flags": {"sup": "good", "ptr": "good"} if rk == 1 else {}})
    return {
        "title": f"Fast movers of {', '.join(chosen_names)} - least rate from all suppliers",
        "notes": [f"Products bought from the chosen suppliers in the last {sales_days} days and sold in >= {min_stores} stores. "
                  f"Strips / month = {sales_days}-day sales / {sales_days} x 30.",
                  f"Rates = bills received in the last {rate_days} days, PTR before GST. Rates >20% below the usual rate are ignored "
                  "(entry errors); own-store bills excluded. RED = another supplier is cheaper than the chosen suppliers."],
        "sheets": [{"name": f"Least Rate {rate_days}D", "columns": cols, "rows": rows},
                   {"name": f"Supplier-wise {rate_days}D", "columns": scols, "rows": srows}],
    }


# ---------------------------------------------------------------- rate difference
def rate_difference(tenant_id, supplier_keys, date_from, date_to, check_gap_pct=20.0):
    ctx = _Ctx(tenant_id)
    d_from, d_to = _day(date_from), _day(date_to)
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_to is before date_from")
    chosen = set(supplier_keys or [])
    L = [r for r in ctx.lines(d_from, d_to + timedelta(days=1)) if not r["internal"] and (not chosen or r["skey"] in chosen)]
    if not L:
        raise HTTPException(status_code=404, detail="No supplier bills for that period")
    for r in L:
        r["month"] = r["date"].strftime("%b-%Y")
        r["mkey"] = (r["key"], r["sale_unit"], r["month"])
        r["paid"] = float(r["ptr"]) * (1 - float(r["disc_pct"]) / 100) * float(r["qty"])
        r["units"] = float(r["qty"]) + float(r["free_qty"])
    grp = defaultdict(list)
    for r in L:
        grp[r["mkey"]].append(r)
    least = {}
    for mk, rs in grp.items():
        guard = _median_guard([r["net"] for r in rs])
        least[mk] = min((r for r in rs if r["net"] >= guard), key=lambda r: (r["net"], r["date"]))
    for r in L:
        lr = least[r["mkey"]]
        r["least"] = lr["net"]
        r["least_at"] = f"{lr['store']} / {ctx.sup_name(lr['skey'])} / bill {lr['grn_no']} ({lr['date']:%d-%m-%Y})"
        r["extra"] = max(0.0, r["net"] - lr["net"])
        r["gap"] = r["extra"] / lr["net"] * 100 if lr["net"] else 0.0
        diff = r["extra"] * r["units"]
        r["loss"], r["check"] = (0.0, diff) if r["gap"] > check_gap_pct else (diff, 0.0)
        r["below"] = r["net"] < lr["net"] - 0.005  # under the guard: probable entry error

    def tot(rs, k):
        return sum(r[k] for r in rs)

    months = sorted({r["month"] for r in L}, key=lambda m: datetime.strptime(m, "%b-%Y"))
    # Summary by supplier
    bys = defaultdict(list)
    for r in L:
        bys[r["skey"]].append(r)
    sum_cols = [_col("sup", "Supplier", width=32), _col("gst", "GST"), _col("bills", "Bills", "int"), _col("lines", "Bill lines", "int"),
                _col("products", "Products", "int"), _col("loss_products", "Products with extra", "int"),
                _col("value", "Purchase value", "money"), _col("loss", "EXTRA PAID", "money"), _col("pct", "Extra %", "pct"),
                _col("check", f"To verify (>{check_gap_pct:g}% gap)", "money")]
    sum_rows = []
    for sk, rs in sorted(bys.items(), key=lambda kv: -tot(kv[1], "loss")):
        v = tot(rs, "paid")
        sum_rows.append({"sup": ctx.sup_name(sk), "gst": sk if not sk.startswith("N:") else "",
                         "bills": len({(r["store"], r["grn_no"]) for r in rs}), "lines": len(rs),
                         "products": len({r["key"] for r in rs}), "loss_products": len({r["key"] for r in rs if r["loss"] > 0.005}),
                         "value": round(v, 2), "loss": round(tot(rs, "loss"), 2), "pct": round(tot(rs, "loss") / v * 100, 2) if v else 0,
                         "check": round(tot(rs, "check"), 2), "_flags": {"loss": "bad"}})
    v = tot(L, "paid")
    sum_rows.append({"sup": "TOTAL", "_total": True, "bills": len({(r["store"], r["grn_no"]) for r in L}), "lines": len(L),
                     "products": len({r["key"] for r in L}), "loss_products": len({r["key"] for r in L if r["loss"] > 0.005}),
                     "value": round(v, 2), "loss": round(tot(L, "loss"), 2), "pct": round(tot(L, "loss") / v * 100, 2) if v else 0,
                     "check": round(tot(L, "check"), 2)})
    # Store x month
    sm_cols = [_col("store", "Store")] + [_col(f"m{i}", m, "money", "Extra paid") for i, m in enumerate(months)] + \
              [_col("total", "Total", "money"), _col("check", "To verify", "money")]
    sm_rows = []
    for s in sorted(ctx.codes, key=lambda s: -sum(r["loss"] for r in L if r["store"] == s)) + ["TOTAL"]:
        rs = [r for r in L if s == "TOTAL" or r["store"] == s]
        if not rs:
            continue
        row = {"store": s, "total": round(tot(rs, "loss"), 2), "check": round(tot(rs, "check"), 2)}
        for i, m in enumerate(months):
            row[f"m{i}"] = round(sum(r["loss"] for r in rs if r["month"] == m), 2)
        if s == "TOTAL":
            row["_total"] = True
        sm_rows.append(row)
    # Product monthly least
    pm_cols = [_col("product", "Product", width=30), _col("pack", "Pack", "int"), _col("month", "Month"),
               _col("least", "Chain least rate", "money"), _col("least_at", "Least rate at (store / supplier / bill)", width=46),
               _col("high", "Highest rate", "money"), _col("gap", "Rate gap %", "pct"), _col("stores", "Stores", "int"),
               _col("suppliers", "Suppliers", "int"), _col("bills", "Bills", "int"), _col("units", "Units", "int"),
               _col("value", "Purchase value", "money"), _col("loss", "Extra paid", "money"), _col("check", "To verify", "money")]
    pm_cols += [_col(f"a_{s}", s, "money", "Avg net rate per store") for s in ctx.codes]
    pm_rows = []
    for mk, rs in sorted(grp.items(), key=lambda kv: -tot(kv[1], "loss")):
        lr = least[mk]
        hi = max(r["net"] for r in rs)
        row = {"product": min((r["product_name"] for r in rs), key=len), "pack": mk[1], "month": mk[2], "least": _r2(lr["net"]),
               "least_at": rs[0]["least_at"], "high": _r2(hi), "gap": round((hi - lr["net"]) / lr["net"] * 100, 1) if lr["net"] else None,
               "stores": len({r["store"] for r in rs}), "suppliers": len({r["skey"] for r in rs}),
               "bills": len({(r["store"], r["grn_no"]) for r in rs}), "units": round(tot(rs, "units")),
               "value": round(tot(rs, "paid"), 2), "loss": round(tot(rs, "loss"), 2), "check": round(tot(rs, "check"), 2)}
        for s in ctx.codes:
            xs = [r for r in rs if r["store"] == s]
            u = sum(r["units"] for r in xs)
            row[f"a_{s}"] = _r2(sum(r["net"] * r["units"] for r in xs) / u) if u else None
        pm_rows.append(row)
    # Bill-wise detail
    bd_cols = [_col("month", "Month"), _col("store", "Store"), _col("sup", "Supplier", width=30), _col("grn", "Bill (GRN) no"),
               _col("date", "Bill date", "date"), _col("code", "Product code"), _col("product", "Product", width=30),
               _col("mrp", "MRP", "money"), _col("qty", "Qty", "int"), _col("free", "Free", "int"), _col("ptr", "PTR", "money"),
               _col("disc", "Disc %", "money"), _col("net", "Net rate", "money"), _col("least", "Chain least", "money"),
               _col("least_at", "Least at (store / supplier / bill)", width=46), _col("extra", "Extra / unit", "money"),
               _col("gap", "Gap %", "pct"), _col("paid", "Amount paid", "money"), _col("loss", "Extra paid", "money"),
               _col("check", "To verify", "money"), _col("note", "Check", width=22)]
    bd_rows = []
    for r in sorted(L, key=lambda r: (r["product_name"], r["date"], r["store"])):
        row = {"month": r["month"], "store": r["store"], "sup": ctx.sup_name(r["skey"]), "grn": r["grn_no"], "date": r["date"],
               "code": r["product_code"], "product": r["product_name"], "mrp": _r2(r["mrp"]), "qty": r["qty"], "free": r["free_qty"],
               "ptr": _r2(r["ptr"]), "disc": _r2(r["disc_pct"]), "net": _r2(r["net"]), "least": _r2(r["least"]),
               "least_at": r["least_at"], "extra": _r2(r["extra"]), "gap": round(r["gap"], 1), "paid": _r2(r["paid"]),
               "loss": _r2(r["loss"]), "check": _r2(r["check"]), "_flags": {}}
        if r["check"] > 0.005:
            row["note"] = f">{check_gap_pct:g}% above least"
            row["_flags"].update(check="warn", note="warn")
        elif r["below"]:
            row["note"] = "far below usual - entry error?"
            row["_flags"]["note"] = "warn"
        elif r["loss"] > 0.005:
            row["_flags"]["loss"] = "bad"
        bd_rows.append(row)
    # Bill summary
    bb = defaultdict(list)
    for r in L:
        bb[(r["store"], r["skey"], r["grn_no"], r["date"])].append(r)
    bs_cols = [_col("store", "Store"), _col("sup", "Supplier", width=30), _col("grn", "Bill (GRN) no"), _col("date", "Bill date", "date"),
               _col("lines", "Lines", "int"), _col("loss_lines", "Lines with extra", "int"), _col("value", "Bill value", "money"),
               _col("loss", "Extra paid", "money"), _col("pct", "Extra %", "pct"), _col("check", "To verify", "money")]
    bs_rows = []
    for (s, sk, g, d), rs in sorted(bb.items(), key=lambda kv: -tot(kv[1], "loss")):
        v = tot(rs, "paid")
        bs_rows.append({"store": s, "sup": ctx.sup_name(sk), "grn": g, "date": d, "lines": len(rs),
                        "loss_lines": sum(1 for r in rs if r["loss"] > 0.005), "value": round(v, 2), "loss": round(tot(rs, "loss"), 2),
                        "pct": round(tot(rs, "loss") / v * 100, 2) if v else 0, "check": round(tot(rs, "check"), 2)})
    who = ", ".join(sorted(ctx.sup_name(k) for k in chosen)) if chosen else "all suppliers"
    return {
        "title": f"Supplier rate difference - {who}",
        "notes": [f"{d_from:%d-%b-%Y} to {d_to:%d-%b-%Y}. Every bill line vs the chain least net rate for the same product, pack "
                  "and month. Net rate = PTR x (1 - disc%) x qty/(qty+free), before GST.",
                  f"Extra paid = (net - least) x units received. Lines more than {check_gap_pct:g}% above the least go to "
                  "'To verify' (usually pack/MRP entry mistakes). A least rate >20% below the usual is ignored as an entry error."],
        "sheets": [{"name": "Summary", "columns": sum_cols, "rows": sum_rows},
                   {"name": "Store x Month", "columns": sm_cols, "rows": sm_rows},
                   {"name": "Product Monthly Least", "columns": pm_cols, "rows": pm_rows},
                   {"name": "Bill-wise Detail", "columns": bd_cols, "rows": bd_rows},
                   {"name": "Bill Summary", "columns": bs_cols, "rows": bs_rows}],
    }
