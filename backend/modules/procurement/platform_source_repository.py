"""Reads of real synchronized platform data (NEXORA_PLATFORM.sync.*).

Used by the end-to-end pipeline and manual product search. These are the same
synced tables the Stock Availability module reads; every row is scoped by
store_id + tenant_id. Read-only.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def read_last_grn(tenant_id, store_id):
    """Latest GRN number synced for the store (sync.PurchaseTrans)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT CAST(MAX(pt.Grnnumber) AS VARCHAR(50))
            FROM sync.PurchaseTrans pt
            WHERE pt.tenant_id = ? AND pt.store_id = ?
            """,
            (tenant_id, store_id),
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None
    finally:
        conn.close()


def read_last_sale_bill(tenant_id, store_id):
    """Latest sale bill number synced for the store (sync.ProductSaleInformation)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT CAST(MAX(psi.BillNumber) AS VARCHAR(50))
            FROM sync.ProductSaleInformation psi
            WHERE psi.tenant_id = ? AND psi.store_id = ?
              AND ISNULL(psi.TransactionValidity, 0) = 0
            """,
            (tenant_id, store_id),
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None
    finally:
        conn.close()


def product_count(tenant_id, store_id):
    """Active product count for the store (sanity/telemetry)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM sync.Products p
            WHERE p.tenant_id = ? AND p.store_id = ? AND ISNULL(p.isActive, 1) = 1
            """,
            (tenant_id, store_id),
        )
        return cursor.fetchone()[0] or 0
    finally:
        conn.close()


def search_products(tenant_id, store_id, query, limit=25):
    """Manual Add Product search over the real Product Master (code or name).

    Barcode search is not available: sync.Products carries no barcode column.
    """
    q = (query or "").strip()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP ({int(limit)})
                CAST(p.ProductCode AS VARCHAR(100)) AS product_code,
                p.ProductName                       AS product_name,
                p.UnitDescription                   AS unit,
                ISNULL(p.TotalStock, 0)             AS current_stock,
                ISNULL(p.MRP, 0)                    AS mrp
            FROM sync.Products p
            WHERE p.tenant_id = ? AND p.store_id = ? AND ISNULL(p.isActive, 1) = 1
              AND ( ? = ''
                    OR p.ProductName LIKE '%' + ? + '%'
                    OR CAST(p.ProductCode AS VARCHAR(50)) LIKE ? + '%' )
            ORDER BY p.ProductName
            """,
            (tenant_id, store_id, q, q, q),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()
