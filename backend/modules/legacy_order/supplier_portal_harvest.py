"""Harvest a portal supplier's live stock and match it to the store's products.

Owner 2026-11-05. The flow (see the Supplier Stock Harvest plan):

 1. When a store's order is processed, the Stock Client finds each supplier that
    has a portal URL + login on its OrderSuppliers row, signs in headlessly, and
    reads that supplier's full product list with stock from the site's own
    rendered catalog.
 2. The client POSTs those rows here. We store them in dbo.SupplierStock (the
    same table the compare card and the Excel import already use) and match each
    supplier product to one of the store's products.
 3. Matching reuses the product_mapping engine (normalization + matcher), so
    "DOLO 650" (store) and "DOLO 650 MG TAB" (supplier) collapse to the same key.
    Each harvested product lands in one of three tiers:
      * matched       -- from SupplierProductMatch, or an exact/normalized/
                         structured auto-match (confident). Saved straight away.
      * suggested     -- a fuzzy match above threshold; flagged for one confirm.
      * needs_mapping -- no confident match; flagged for the user to map once.
 4. Confirming a suggestion or mapping an unmapped product writes
    SupplierProductMatch, so next time it is a known exact match.

No credentials or site sessions live here -- the headless login + read happen on
the store PC (the Stock Client), which already holds the encrypted login. This
module only stores the stock it is handed and does the matching.
"""
from __future__ import annotations

import datetime as _dt

from modules.legacy_order import database
from modules.product_mapping import matcher, normalization

# A fuzzy decision at or above this score is auto-suggested (amber, one confirm);
# below it the product needs manual mapping (red). Tunable once we see real
# per-supplier numbers.
SUGGEST_THRESHOLD = 0.60

# SupplierStock columns we write (the legacy table the compare card reads).
_STOCK_COLS = (
    "suppliercode", "supplierproductcode", "supplierproductname", "mrp", "ptr",
    "stock", "discound", "packing", "storename", "sch", "free", "transactiondate",
)


# ---- helpers ---------------------------------------------------------------

def _store(store_name):
    store = str(store_name or "").strip()
    if not store or len(store) > 50:
        raise ValueError("Pick a store first.")
    return store


def _supplier(supplier_code):
    code = str(supplier_code or "").strip()
    if not code or len(code) > 200:
        raise ValueError("Pick a supplier first.")
    return code


def _num(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _int(value):
    n = _num(value)
    return int(n) if n is not None else None


def _dosage_terms(conn):
    """The configurable strip vocabulary; falls back to the engine default."""
    try:
        rows = conn.cursor().execute(
            "SELECT term FROM dbo.product_normalization_dictionary WHERE IsActive = 1"
        ).fetchall()
        terms = {str(r[0]).strip().upper() for r in rows if r[0]}
        if terms:
            return terms
    except Exception:
        pass
    return set(normalization.DEFAULT_DOSAGE_TERMS)


# ---- store the harvested stock ---------------------------------------------

def replace_supplier_stock(conn, store, supplier_code, rows):
    """Replace this supplier+store's SupplierStock with the freshly harvested
    rows (a harvest is a full snapshot of the supplier's catalog)."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM dbo.SupplierStock WHERE suppliercode = ? AND storename = ?",
        supplier_code, store,
    )
    today = _dt.date.today()
    placeholders = ", ".join("?" for _ in _STOCK_COLS)
    prepared = []
    for r in rows:
        name = " ".join(str(r.get("name") or "").split())
        if not name:
            continue
        prepared.append((
            supplier_code,
            str(r.get("code") or "").strip()[:100] or None,
            name[:200],
            _num(r.get("mrp")),
            _num(r.get("ptr")),
            _int(r.get("stock")) or 0,
            _num(r.get("discount")),
            str(r.get("packing") or "").strip()[:100] or None,
            store,
            str(r.get("scheme") or "").strip()[:100] or None,
            _int(r.get("free")) or 0,
            today,
        ))
    if prepared:
        cur.executemany(
            f"INSERT INTO dbo.SupplierStock ({', '.join(_STOCK_COLS)}) "
            f"VALUES ({placeholders})",
            prepared,
        )
    return len(prepared)


# ---- match the harvested products to the store's products ------------------

def _store_products(conn):
    """The store's product catalog as matcher target rows."""
    rows = conn.cursor().execute(
        "SELECT ProductCode, ProductName, MRP FROM dbo.Products "
        "WHERE ProductName IS NOT NULL AND LTRIM(RTRIM(ProductName)) <> ''"
    ).fetchall()
    return [{"product_code": str(r[0]), "product_name": r[1], "mrp": _num(r[2])} for r in rows]


def _known_pairs(conn, store, supplier_code):
    """Existing (supplierProductCode -> ProductCode) links for this supplier."""
    rows = conn.cursor().execute(
        "SELECT SupplierProductCode, ProductCode FROM dbo.SupplierProductMatch "
        "WHERE SupplierCode = ? AND StoreName = ? AND IsActive = 1 "
        "AND SupplierProductCode IS NOT NULL AND ProductCode IS NOT NULL",
        supplier_code, store,
    ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _tier(decision):
    """matched / suggested / needs_mapping from a matcher decision."""
    if decision["target_product_code"] and decision["status"] == "AUTO":
        return "matched"
    if decision["target_product_code"] and decision["confidence"] >= SUGGEST_THRESHOLD:
        return "suggested"
    return "needs_mapping"


def match_harvest(conn, store, supplier_code, rows):
    """Match each harvested supplier product to a store product. Returns a list
    of {supplier_code, supplier_name, product_code?, product_name?, stock, mrp,
    tier, confidence, method, candidates}."""
    terms = _dosage_terms(conn)
    targets = _store_products(conn)
    pairs = _known_pairs(conn, store, supplier_code)
    sources = []
    for r in rows:
        name = " ".join(str(r.get("name") or "").split())
        if not name:
            continue
        sources.append({
            "product_code": str(r.get("code") or name),  # supplier's own code, or its name
            "product_name": name,
            "mrp": _num(r.get("mrp")),
            "_stock": _int(r.get("stock")) or 0,
        })
    decisions = matcher.match_products(sources, targets, supplier_pairs=pairs, dosage_terms=terms)
    stock_by_src = {s["product_code"]: s["_stock"] for s in sources}
    out = []
    for d in decisions:
        out.append({
            "supplier_code": d["source_product_code"],
            "supplier_name": d["source_product_name"],
            "product_code": d["target_product_code"],
            "product_name": d["target_product_name"],
            "stock": stock_by_src.get(d["source_product_code"], 0),
            "mrp": d["mrp"],
            "tier": _tier(d),
            "confidence": d["confidence"],
            "method": d["match_method"],
            "candidates": [
                {"product_code": c.get("target_product_code"),
                 "product_name": c.get("target_product_name"),
                 "score": c.get("total_score")}
                for c in (d.get("candidates") or [])[:5]
            ],
        })
    return out


# ---- the public operations the router calls --------------------------------

def harvest(store_name, supplier_code, rows, actor=None):
    """Store the harvested stock and return the match review (by tier)."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    with database.get_central_connection() as conn:
        stored = replace_supplier_stock(conn, store, supplier, rows)
        matches = match_harvest(conn, store, supplier, rows)
        # Auto-save the confident matches to SupplierProductMatch so next time
        # they are known (phase 1) -- only the 'matched' tier, never suggestions.
        saved = 0
        for m in matches:
            if m["tier"] == "matched" and m["product_code"]:
                saved += _upsert_match(conn, store, supplier, m["supplier_code"],
                                       m["supplier_name"], m["product_code"], actor)
        conn.commit()
    counts = {"matched": 0, "suggested": 0, "needs_mapping": 0}
    for m in matches:
        counts[m["tier"]] += 1
    return {"stored": stored, "auto_saved": saved, "counts": counts, "items": matches}


def _upsert_match(conn, store, supplier_code, sup_product_code, sup_product_name, product_code, actor):
    """Insert or update one SupplierProductMatch link. Returns 1 if written."""
    cur = conn.cursor()
    updated = cur.execute(
        "UPDATE dbo.SupplierProductMatch SET ProductCode = ?, SupplierProductName = ?, "
        "UserName = ?, LastModifiedDate = GETDATE(), IsActive = 1 "
        "WHERE SupplierCode = ? AND StoreName = ? AND SupplierProductCode = ?",
        product_code, sup_product_name, actor, supplier_code, store, sup_product_code,
    ).rowcount
    if not updated:
        cur.execute(
            "INSERT INTO dbo.SupplierProductMatch "
            "(SupplierCode, SupplierProductCode, SupplierProductName, ProductCode, "
            " UserName, LastModifiedDate, IsActive, StoreName) "
            "VALUES (?, ?, ?, ?, ?, GETDATE(), 1, ?)",
            supplier_code, sup_product_code, sup_product_name, product_code, actor, store,
        )
    return 1


def confirm_match(store_name, supplier_code, sup_product_code, sup_product_name, product_code, actor=None):
    """Confirm a suggestion / map an unmapped product -> SupplierProductMatch."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    code = str(sup_product_code or sup_product_name or "").strip()
    if not code:
        raise ValueError("Pick the supplier product.")
    target = str(product_code or "").strip()
    with database.get_central_connection() as conn:
        if target:
            if not conn.cursor().execute(
                "SELECT TOP 1 1 FROM dbo.Products WHERE ProductCode = ?", target
            ).fetchone():
                raise LookupError("That product no longer exists.")
            _upsert_match(conn, store, supplier, code, sup_product_name, target, actor)
        else:
            # Unmap: clear the link (leave the row inactive).
            conn.cursor().execute(
                "UPDATE dbo.SupplierProductMatch SET IsActive = 0, UserName = ?, "
                "LastModifiedDate = GETDATE() WHERE SupplierCode = ? AND StoreName = ? "
                "AND SupplierProductCode = ?", actor, supplier, store, code,
            )
        conn.commit()
    return {"ok": True}


def review(store_name, supplier_code):
    """Re-derive the match review from the stored SupplierStock (no re-harvest)."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(
            "SELECT supplierproductcode, supplierproductname, stock, mrp, ptr, packing "
            "FROM dbo.SupplierStock WHERE suppliercode = ? AND storename = ?",
            supplier, store,
        ).fetchall()
        harvested = [{"code": r[0], "name": r[1], "stock": r[2], "mrp": r[3],
                      "ptr": r[4], "packing": r[5]} for r in rows]
        matches = match_harvest(conn, store, supplier, harvested)
    counts = {"matched": 0, "suggested": 0, "needs_mapping": 0}
    for m in matches:
        counts[m["tier"]] += 1
    return {"counts": counts, "items": matches}
