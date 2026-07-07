"""Read-only access to the synced product source (the engine's INPUT).

Reads the same platform-synced tables Procurement/Stock use:
  * ``sync.Products`` — per-store product master (ProductCode, ProductName, MRP).
  * ``sync.SupplierProductMatch`` — supplier↔store ProductCode links, used to
    derive Phase-1 cross-store pairs.

Crucially, the supplier pairs are derived by joining on
``(SupplierCode, SupplierProductCode)`` across the two stores — NOT on equal
ProductCode. Two stores that both stock the same supplier line resolve to their
respective (possibly different) ProductCodes, giving a trustworthy 100% pair.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def _object_exists(cursor, name):
    cursor.execute("SELECT OBJECT_ID(?)", (name,))
    return cursor.fetchone()[0] is not None


def load_store_products(tenant_id, store_id):
    """Active products for one store: ``[{product_code, product_name, mrp}]``."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(p.ProductCode AS VARCHAR(50))        AS product_code,
                   p.ProductName                             AS product_name,
                   CAST(ISNULL(p.MRP, 0) AS DECIMAL(18,2))   AS mrp
            FROM sync.Products p
            WHERE p.tenant_id = ? AND p.store_id = ?
              AND ISNULL(p.isActive, 1) = 1
              AND p.ProductName IS NOT NULL
            """,
            (tenant_id, store_id),
        )
        rows = _rows_to_dicts(cur)
        for r in rows:
            r["mrp"] = float(r["mrp"]) if r["mrp"] is not None else None
        return rows
    finally:
        conn.close()


def search_store_products(tenant_id, store_id, query, limit=25):
    """Server-side product lookup in one store for the Correct-Product picker.

    Multi-token AND match on ``ProductName`` (so ``crocin 500 tab`` narrows on
    brand + strength + form, all of which live inside the name) plus a
    ProductCode prefix match. Same source table the engine reads, so a picked
    product is always a real, mappable target. Returns
    ``[{product_code, product_name, unit, mrp}]`` ordered by name.
    """
    q = (query or "").strip()
    tokens = [t for t in q.split() if t][:6]
    conn = get_connection()
    try:
        cur = conn.cursor()
        where = ["p.tenant_id = ?", "p.store_id = ?", "ISNULL(p.isActive, 1) = 1",
                 "p.ProductName IS NOT NULL"]
        params = [tenant_id, store_id]
        # Relevance rank (lower = better): exact code, exact name, name starts-with,
        # code starts-with, then contains (which also covers brand / strength /
        # form / generic tokens, since those live inside ProductName). Ties break
        # by shortest name then alphabetically.
        rank = "0"
        order_params = []
        if tokens:
            name_clause = " AND ".join(["p.ProductName LIKE '%' + ? + '%'"] * len(tokens))
            params.extend(tokens)
            where.append(
                f"(({name_clause}) OR CAST(p.ProductCode AS VARCHAR(50)) LIKE ? + '%')")
            params.append(q)
            rank = """
                CASE
                    WHEN CAST(p.ProductCode AS VARCHAR(50)) = ?      THEN 0
                    WHEN p.ProductName = ?                          THEN 1
                    WHEN p.ProductName LIKE ? + '%'                 THEN 2
                    WHEN CAST(p.ProductCode AS VARCHAR(50)) LIKE ? + '%' THEN 3
                    ELSE 4
                END"""
            order_params = [q, q, q, q]
        cur.execute(
            f"""
            SELECT TOP ({int(limit)})
                   CAST(p.ProductCode AS VARCHAR(50))      AS product_code,
                   p.ProductName                           AS product_name,
                   p.UnitDescription                       AS unit,
                   CAST(ISNULL(p.MRP, 0) AS DECIMAL(18,2)) AS mrp
            FROM sync.Products p
            WHERE {' AND '.join(where)}
            ORDER BY {rank}, LEN(p.ProductName), p.ProductName
            """,
            tuple(params + order_params),
        )
        rows = _rows_to_dicts(cur)
        for r in rows:
            r["mrp"] = float(r["mrp"]) if r["mrp"] is not None else None
        return rows
    finally:
        conn.close()


def load_supplier_pairs(tenant_id, source_store_id, target_store_id):
    """Phase-1 cross-store pairs ``[(source_code, target_code)]`` derived from
    the supplier match table joined on (SupplierCode, SupplierProductCode).

    Returns an empty list when the match table is not provisioned."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not _object_exists(cur, "sync.SupplierProductMatch"):
            return []
        cur.execute(
            """
            SELECT DISTINCT
                   CAST(s.ProductCode AS VARCHAR(50)) AS source_code,
                   CAST(t.ProductCode AS VARCHAR(50)) AS target_code
            FROM sync.SupplierProductMatch s
            JOIN sync.SupplierProductMatch t
              ON t.tenant_id = s.tenant_id
             AND t.SupplierCode = s.SupplierCode
             AND t.SupplierProductCode = s.SupplierProductCode
             AND t.store_id = ?
            WHERE s.tenant_id = ? AND s.store_id = ?
              AND s.ProductCode IS NOT NULL AND t.ProductCode IS NOT NULL
            """,
            (target_store_id, tenant_id, source_store_id),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        conn.close()
