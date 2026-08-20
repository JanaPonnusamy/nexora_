"""Chunk 10 — Product Resolution Engine. MASTER_PRODUCT data access.

Reads sync.SupplierProductMatch ("SupplierProductMapping" in the module
brief) joined to sync.Products (the real per-store product master) — the
same synced tables modules/product_mapping/source_repository.py reads, kept
in its own file here rather than repository.py because it queries a
different schema family (sync.* vs this module's own dbo.doc_*).

Never writes either table — this module has no write path into the
platform's real product master, only into its own dbo.doc_product_mapping
(repository.py).
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts
from modules.product_mapping.normalization import normalize_product_name


def find_master_product(tenant_id, store_id, supplier_code, normalized_product_key):
    """This supplier's known products (from sync.SupplierProductMatch,
    joined to sync.Products for the display name), matched in Python against
    normalized_product_key — the same normalize-then-compare shape as
    supplier_engine's name matching, since SQL Server has no equivalent of
    normalize_product_name() to push the comparison server-side. None if no
    row's normalized name matches."""
    if not supplier_code:
        return None
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT OBJECT_ID('sync.SupplierProductMatch')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute(
            """
            SELECT m.SupplierProductName AS supplier_product_name,
                   CAST(p.ProductCode AS VARCHAR(50)) AS product_code,
                   p.ProductName AS product_name
            FROM sync.SupplierProductMatch m
            JOIN sync.Products p
                ON p.tenant_id = m.tenant_id AND p.store_id = m.store_id
               AND CAST(p.ProductCode AS VARCHAR(50)) = CAST(m.ProductCode AS VARCHAR(50))
            WHERE m.tenant_id = ? AND m.store_id = ? AND m.SupplierCode = ?
              AND m.ProductCode IS NOT NULL
              AND (m.IsActive = 1 OR m.IsActive IS NULL)
            """,
            (tenant_id, store_id, supplier_code),
        )
        rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    for row in rows:
        if normalize_product_name(row["supplier_product_name"]) == normalized_product_key:
            return row
    return None


def master_product_code_exists(tenant_id, store_id, product_code) -> bool:
    """Existence check for the ProductCode Integrity Rule (service-layer
    enforcement, since doc_import_item.product_code has no FK — see
    product_resolution.validate_product_code_integrity, the caller). A
    MASTER_PRODUCT-sourced code must be a real row in sync.Products for this
    tenant/store."""
    if not product_code:
        return False
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT OBJECT_ID('sync.Products')")
        if cur.fetchone()[0] is None:
            return False
        cur.execute(
            """
            SELECT 1 FROM sync.Products
            WHERE tenant_id = ? AND store_id = ? AND CAST(ProductCode AS VARCHAR(50)) = ?
            """,
            (tenant_id, store_id, str(product_code)),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()
