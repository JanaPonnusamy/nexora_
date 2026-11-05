"""Map a supplier's harvested products to the store's products.

Owner 2026-11-05 — a SEPARATE concern from harvesting the stock. The harvest
(supplier_stock_harvest.py) fills dbo.SupplierStock. The existing Live Stock mode
only shows products that are already in dbo.SupplierProductMatch, so the products
a supplier stocks but that are not mapped yet stay invisible until they are
mapped. This module is the "Map supplier products" panel's backend:

  * review()  — read the supplier's SupplierStock, match each product to the
    store's Products via the product_mapping engine (reusing the 383k existing
    SupplierProductMatch pairs), and classify into three tiers:
      - matched       : an explicit SupplierProductMatch pair, or an exact /
                        normalized / structured auto-match (confident).
      - suggested     : a fuzzy match at/above SUGGEST_THRESHOLD — one confirm.
      - needs_mapping : no confident match — the user maps it once.
  * confirm() — write the user's chosen (supplier product -> store product) to
    SupplierProductMatch, so it is a known match next time and shows in Live
    Stock. Blank product_code unmaps.

This module never touches SupplierStock and never searches the site; it only
reads harvested stock and writes mappings.
"""
from __future__ import annotations

from modules.legacy_order import database
from modules.product_mapping import matcher, normalization

# A fuzzy decision at/above this score is auto-suggested (amber, one confirm);
# below it the product needs manual mapping (red). Tunable.
SUGGEST_THRESHOLD = 0.60


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


def _dosage_terms(conn):
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


def _store_products(conn):
    rows = conn.cursor().execute(
        "SELECT ProductCode, ProductName, MRP FROM dbo.Products "
        "WHERE ProductName IS NOT NULL AND LTRIM(RTRIM(ProductName)) <> ''"
    ).fetchall()
    return [{"product_code": str(r[0]), "product_name": r[1], "mrp": _num(r[2])} for r in rows]


def _known_pairs(conn, store, supplier_code):
    rows = conn.cursor().execute(
        "SELECT SupplierProductCode, ProductCode FROM dbo.SupplierProductMatch "
        "WHERE SupplierCode = ? AND StoreName = ? AND IsActive = 1 "
        "AND SupplierProductCode IS NOT NULL AND ProductCode IS NOT NULL",
        supplier_code, store,
    ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _supplier_stock(conn, store, supplier_code):
    rows = conn.cursor().execute(
        "SELECT supplierproductcode, supplierproductname, stock, mrp "
        "FROM dbo.SupplierStock WHERE suppliercode = ? AND storename = ?",
        supplier_code, store,
    ).fetchall()
    return rows


def _tier(decision):
    if decision["target_product_code"] and decision["status"] == "AUTO":
        return "matched"
    if decision["target_product_code"] and decision["confidence"] >= SUGGEST_THRESHOLD:
        return "suggested"
    return "needs_mapping"


def review(store_name, supplier_code):
    """Match the supplier's harvested stock to the store's products, by tier."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    with database.get_central_connection() as conn:
        terms = _dosage_terms(conn)
        targets = _store_products(conn)
        pairs = _known_pairs(conn, store, supplier)
        stock_rows = _supplier_stock(conn, store, supplier)
    sources, stock_by_src = [], {}
    for r in stock_rows:
        name = " ".join(str(r[1] or "").split())
        if not name:
            continue
        code = str(r[0] or name)
        sources.append({"product_code": code, "product_name": name, "mrp": _num(r[3])})
        stock_by_src[code] = int(r[2] or 0)
    decisions = matcher.match_products(sources, targets, supplier_pairs=pairs, dosage_terms=terms)
    items, counts = [], {"matched": 0, "suggested": 0, "needs_mapping": 0}
    for d in decisions:
        tier = _tier(d)
        counts[tier] += 1
        items.append({
            "supplier_code": d["source_product_code"],
            "supplier_name": d["source_product_name"],
            "product_code": d["target_product_code"],
            "product_name": d["target_product_name"],
            "stock": stock_by_src.get(d["source_product_code"], 0),
            "mrp": d["mrp"],
            "tier": tier,
            "confidence": d["confidence"],
            "method": d["match_method"],
            "candidates": [
                {"product_code": c.get("target_product_code"),
                 "product_name": c.get("target_product_name"),
                 "score": c.get("total_score")}
                for c in (d.get("candidates") or [])[:5]
            ],
        })
    return {"counts": counts, "items": items}


def _upsert_match(cur, store, supplier_code, sup_product_code, sup_product_name, product_code, actor):
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


def confirm(store_name, supplier_code, sup_product_code, sup_product_name, product_code, actor=None):
    """Save the user's chosen mapping to SupplierProductMatch. Blank product_code
    unmaps (marks the pair inactive)."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    code = str(sup_product_code or sup_product_name or "").strip()
    if not code:
        raise ValueError("Pick the supplier product.")
    target = str(product_code or "").strip()
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        if target:
            if not cur.execute("SELECT TOP 1 1 FROM dbo.Products WHERE ProductCode = ?", target).fetchone():
                raise LookupError("That product no longer exists.")
            _upsert_match(cur, store, supplier, code, sup_product_name, target, actor)
        else:
            cur.execute(
                "UPDATE dbo.SupplierProductMatch SET IsActive = 0, UserName = ?, "
                "LastModifiedDate = GETDATE() WHERE SupplierCode = ? AND StoreName = ? "
                "AND SupplierProductCode = ?", actor, supplier, store, code,
            )
        conn.commit()
    return {"ok": True}
