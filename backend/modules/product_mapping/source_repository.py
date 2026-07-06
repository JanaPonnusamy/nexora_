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
