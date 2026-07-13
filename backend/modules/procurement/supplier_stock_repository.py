"""Read-only data access for Supplier Live Stock (Sprint 2 — Workspace Completion).

Intersects a supplier's imported live-stock file (procurement.supplier_stock)
with the current Refresh VPL (procurement.procurement_virtual_products), returning
only products that (a) exist in the current VPL, (b) are mapped to a store
ProductCode and (c) have supplier stock > 0. Suggested / Final quantities come
from the working order items for the same Refresh.

Pure read. No inserts, no updates, no calculations. Product-code mapping is
resolved at import time (via SupplierProductMatch); when a match table is present
it is also honoured here as a fallback, but no mapping logic is created.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def _object_exists(cursor, name):
    cursor.execute("SELECT OBJECT_ID(?)", (name,))
    return cursor.fetchone()[0] is not None


def get_supplier_stock(tenant_id, refresh_id, supplier_code, store_id=None, search=None, only_available=True):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Import target may not be provisioned yet — degrade to an empty list.
        if not _object_exists(cursor, "procurement.supplier_stock"):
            return []

        # product_code is resolved once at import time (via SupplierProductMatch),
        # so the live query is a cheap supplier_stock ⋈ VPL on the store ProductCode
        # — no giant runtime match join. Rows that never mapped simply won't
        # intersect the VPL (correct — the store cannot stock an unmapped product).
        product_code_expr = "CAST(ss.product_code AS VARCHAR(100))"

        search_term = (search or "").strip()
        only_flag = 1 if only_available else 0
        # store filter is applied only when the refresh's store is known.
        store_clause = "AND ss.store_id = ?" if store_id else ""

        sql = f"""
            SELECT
                CAST(ss.supplier_code AS VARCHAR(100))          AS supplier_code,
                CAST(ss.supplier_product_code AS VARCHAR(100))  AS supplier_product_code,
                ss.supplier_product_name                        AS supplier_product_name,
                CAST(vp.product_code AS VARCHAR(100))           AS product_code,
                vp.product_name                                 AS product_name,
                ss.available_stock                              AS available_stock,
                ss.ptr                                          AS ptr,
                ss.mrp                                          AS mrp,
                ss.discount                                     AS discount,
                ss.packing                                      AS packing,
                ss.free                                         AS free,
                ss.minimum_qty                                  AS minimum_qty,
                ss.scheme                                       AS scheme,
                ss.transaction_date                             AS transaction_date,
                oi.suggested_qty                                AS suggested_qty,
                oi.final_qty                                    AS final_qty
            FROM procurement.supplier_stock ss
            INNER JOIN procurement.procurement_virtual_products vp
                ON vp.tenant_id = ss.tenant_id
               AND vp.refresh_id = ?
               AND vp.is_active = 1
               AND CAST(vp.product_code AS VARCHAR(100)) = {product_code_expr}
            LEFT JOIN procurement.procurement_order_items oi
                ON oi.tenant_id = ss.tenant_id
               AND oi.refresh_id = ?
               AND oi.product_id = vp.product_id
               AND oi.is_deleted = 0
            WHERE ss.tenant_id = ?
              AND ss.supplier_code = ?
              {store_clause}
              AND ss.is_active = 1
              AND (? = 0 OR ISNULL(ss.available_stock, 0) > 0)
              AND ( ? = ''
                    OR ss.supplier_product_name LIKE '%' + ? + '%'
                    OR CAST(vp.product_code AS VARCHAR(100)) LIKE ? + '%'
                    OR vp.product_name LIKE '%' + ? + '%' )
            ORDER BY ss.supplier_product_name
        """
        params = [refresh_id, refresh_id, tenant_id, supplier_code]
        if store_id:
            params.append(store_id)
        params.extend([only_flag, search_term, search_term, search_term, search_term])
        params = tuple(params)
        cursor.execute(sql, params)
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def products_with_offers(tenant_id, refresh_id, store_id=None):
    """Distinct product codes IN THIS REFRESH'S VPL that carry an offer —
    the "Has Offer" filter source for Review All / Supplier Purchasing.

    Two sources, unioned:
      1. sync.PurchaseTrans — the product's most recent purchase from ANY
         supplier came with free qty or a discount %. Same offer semantics
         the Export Monitor shows in its Offer / Dis% columns
         (assignment_repository.list_by_refresh), so what the buyer filters
         on is exactly what the purchase history displays. This is the
         source that always has data.
      2. procurement.supplier_stock — a supplier's live-stock import is
         currently advertising a scheme/free/discount. Fresher when it
         exists, but it only exists for suppliers whose stock file has been
         imported, so it can never be the only source (it was, and the
         filter came back empty on every store without an import).
    Read-only; each source degrades to nothing if its table isn't provisioned."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        codes = set()

        # 1. Offers evidenced by the product's own purchase history.
        if store_id and _object_exists(cursor, "sync.PurchaseTrans"):
            cursor.execute(
                """
                WITH vpl AS (
                    SELECT DISTINCT CAST(vp.product_code AS VARCHAR(100)) AS product_code
                    FROM procurement.procurement_virtual_products vp
                    WHERE vp.tenant_id = ? AND vp.refresh_id = ? AND vp.is_active = 1
                ),
                latest AS (
                    SELECT v.product_code, pt.FreeQty, pt.ProductDiscPercent,
                        ROW_NUMBER() OVER (
                            PARTITION BY v.product_code
                            ORDER BY pt.grndate DESC, pt.Grnnumber DESC
                        ) AS rnk
                    FROM vpl v
                    JOIN sync.PurchaseTrans pt
                        ON pt.tenant_id = ? AND pt.store_id = ?
                       AND pt.ProductCode = TRY_CAST(v.product_code AS INT)
                )
                SELECT product_code FROM latest
                WHERE rnk = 1
                  AND ( ISNULL(FreeQty, 0) > 0 OR ISNULL(ProductDiscPercent, 0) > 0 )
                """,
                (tenant_id, refresh_id, tenant_id, store_id),
            )
            codes.update(r[0] for r in cursor.fetchall())

        # 2. Offers a supplier is advertising right now in its live stock.
        if _object_exists(cursor, "procurement.supplier_stock"):
            store_clause = "AND ss.store_id = ?" if store_id else ""
            sql = f"""
                SELECT DISTINCT CAST(vp.product_code AS VARCHAR(100)) AS product_code
                FROM procurement.supplier_stock ss
                INNER JOIN procurement.procurement_virtual_products vp
                    ON vp.tenant_id = ss.tenant_id
                   AND vp.refresh_id = ?
                   AND vp.is_active = 1
                   AND CAST(vp.product_code AS VARCHAR(100)) = CAST(ss.product_code AS VARCHAR(100))
                WHERE ss.tenant_id = ?
                  {store_clause}
                  AND ss.is_active = 1
                  -- discount is VARCHAR and holds messy free-text in this dataset
                  -- (e.g. "16% MICRO CARSYON 1"), not a clean percentage — a
                  -- numeric compare on it crashes on the non-numeric rows, so any
                  -- present, non-empty value counts as an offer signal instead.
                  AND ( ss.scheme IS NOT NULL
                        OR ISNULL(ss.free, 0) > 0
                        OR (ss.discount IS NOT NULL AND ss.discount <> '') )
            """
            params = [refresh_id, tenant_id]
            if store_id:
                params.append(store_id)
            cursor.execute(sql, tuple(params))
            codes.update(r[0] for r in cursor.fetchall())

        return sorted(codes)
    finally:
        conn.close()
