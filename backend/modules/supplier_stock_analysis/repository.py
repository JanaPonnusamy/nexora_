"""Data access for Supplier Stock Analysis.

Supplier live stock is read from (and Excel imports write to) the central
legacy ``OrderNMC.dbo.SupplierStock`` table -- the same table the legacy
order screens and the Order Workspace use -- so there is ONE supplier stock
for every screen. Everything else (stores, products, mappings, sync.*) is
NEXORA_PLATFORM. Both databases live on the same SQL Server instance, so the
OrderNMC rows are joined in cross-database.
"""

import os
import re

from config.database import get_connection
from modules.legacy_order import database as legacy_database
from modules.procurement._dbutil import rows_to_dicts


def _ordernmc():
    name = os.getenv("LEGACY_DB_DATABASE", "OrderNMC")
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError(f"Invalid LEGACY_DB_DATABASE: {name!r}")
    return f"[{name}]"


def _supplier_stock_source():
    """OrderNMC.SupplierStock shaped like the old procurement.supplier_stock
    table, so the analysis queries below keep their column names. The legacy
    storename is the store CODE; product_code resolves through the store's
    OrderNMC SupplierProductMatch (unique per store+supplier+product, same
    join the legacy order screens use). OrderNMC is Latin1_General_CI_AI and
    NEXORA_PLATFORM is SQL_Latin1_General_CP1_CI_AS, hence the COLLATEs.
    supplier_stock_id is the hex of storename|supplier|product (URL-safe,
    decoded by supplier_stock_row)."""
    db = _ordernmc()
    return f"""(
        SELECT
            st.tenant_id,
            st.store_id,
            CONVERT(VARCHAR(400), CAST(s.storename + CHAR(31) + s.suppliercode + CHAR(31)
                + s.supplierproductcode AS VARBINARY(200)), 2) AS supplier_stock_id,
            s.storename COLLATE DATABASE_DEFAULT AS store_code,
            s.suppliercode COLLATE DATABASE_DEFAULT AS supplier_code,
            s.supplierproductcode COLLATE DATABASE_DEFAULT AS supplier_product_code,
            s.supplierproductname COLLATE DATABASE_DEFAULT AS supplier_product_name,
            CAST(spm.ProductCode AS VARCHAR(50)) AS product_code,
            s.stock AS available_stock,
            s.ptr,
            s.mrp,
            s.discound COLLATE DATABASE_DEFAULT AS discount,
            s.packing COLLATE DATABASE_DEFAULT AS packing,
            s.free,
            s.minqty AS minimum_qty,
            s.sch AS scheme,
            s.Rack COLLATE DATABASE_DEFAULT AS rack,
            s.transactiondate AS transaction_date,
            s.transactiondate AS imported_at,
            'ordernmc' AS source,
            1 AS is_active
        FROM {db}.dbo.SupplierStock s
        JOIN dbo.stores st
          ON st.store_code = s.storename COLLATE DATABASE_DEFAULT
        LEFT JOIN {db}.dbo.SupplierProductMatch spm
          ON spm.StoreName = s.storename
         AND spm.SupplierCode = s.suppliercode
         AND spm.SupplierProductCode = s.supplierproductcode
    )"""


def _store_code(tenant_id, store_id):
    rows = _fetch(
        "SELECT store_code FROM dbo.stores WHERE tenant_id = ? AND store_id = ?",
        (tenant_id, store_id),
    )
    return (rows[0]["store_code"] or "").strip() if rows else None


def _fetch(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def list_suppliers(tenant_id, store_id=None, search=""):
    conn = get_connection()
    try:
        cur = conn.cursor()
        store_clause = "AND ss.store_id = ?" if store_id else ""
        params = [tenant_id]
        if store_id:
            params.append(store_id)
        term = (search or "").strip()
        params.extend([term, term, term])
        db = _ordernmc()
        # Supplier name: the store's own OrderSuppliers row (what the legacy
        # order screens show), falling back to the synced store master.
        cur.execute(
            f"""
            SELECT x.supplier_code, x.supplier_name, x.product_count,
                   x.available_count, x.total_available_stock, x.last_imported_at
            FROM (
                SELECT
                    ss.supplier_code,
                    COALESCE(
                        MAX(NULLIF(RTRIM(os.Suppliername COLLATE DATABASE_DEFAULT), '')),
                        MAX(NULLIF(RTRIM(s.suppliername), '')),
                        ''
                    ) AS supplier_name,
                    COUNT(1) AS product_count,
                    SUM(CASE WHEN ISNULL(ss.available_stock, 0) > 0 THEN 1 ELSE 0 END) AS available_count,
                    SUM(ISNULL(ss.available_stock, 0)) AS total_available_stock,
                    MAX(ss.imported_at) AS last_imported_at
                FROM {_supplier_stock_source()} ss
                LEFT JOIN {db}.dbo.OrderSuppliers os
                    ON os.StoreName COLLATE DATABASE_DEFAULT = ss.store_code
                   AND os.suppliercode COLLATE DATABASE_DEFAULT = ss.supplier_code
                LEFT JOIN sync.Suppliers s
                    ON s.tenant_id = ss.tenant_id
                   AND s.store_id = ss.store_id
                   AND CAST(s.suppliercode AS VARCHAR(100)) = ss.supplier_code
                WHERE ss.tenant_id = ?
                  {store_clause}
                GROUP BY ss.supplier_code
            ) x
            WHERE ? = ''
               OR x.supplier_code LIKE ? + '%'
               OR x.supplier_name LIKE '%' + ? + '%'
            ORDER BY x.supplier_name, x.supplier_code
            """,
            tuple(params),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def list_order_suppliers(tenant_id, store_id):
    """Every supplier on the store's OrderNMC.OrderSuppliers list -- the
    choices for an Excel import (a supplier need not have stock rows yet)."""
    store_code = _store_code(tenant_id, store_id)
    if not store_code:
        return []
    with legacy_database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT RTRIM(suppliercode) AS supplier_code, RTRIM(ISNULL(Suppliername, '')) AS supplier_name "
            "FROM OrderSuppliers WHERE StoreName = ? AND ISNULL(IsActive, 1) = 1 "
            "ORDER BY Suppliername, suppliercode",
            (store_code,),
        )
        return rows_to_dicts(cur)


def list_supplier_products(tenant_id, supplier_code, store_id=None, search="", only_available=True):
    conn = get_connection()
    try:
        cur = conn.cursor()
        store_clause = "AND ss.store_id = ?" if store_id else ""
        term = (search or "").strip()
        # Placeholder order must match the CTEs below, top to bottom.
        params = [tenant_id]                       # active_store_count
        params += [tenant_id, supplier_code]       # supplier_keys
        if store_id:
            params.append(store_id)
        params += [tenant_id, tenant_id]           # map_resolved (source + target sides)
        params += [tenant_id]                       # mapagg (sync.Products.tenant_id, other-store stock join)
        params += [tenant_id, supplier_code]       # final WHERE
        if store_id:
            params.append(store_id)
        params += [1 if only_available else 0, term, term, term, term]
        cur.execute(
            f"""
            WITH active_store_count AS (
                SELECT COUNT(1) AS total_store_count
                FROM dbo.stores
                WHERE tenant_id = ?
                  AND ISNULL(is_active, 1) = 1
            ),
            -- Distinct (store, product_code) keys this supplier actually has, so
            -- the cross-store mapping walk runs ONCE set-based instead of as a
            -- correlated OUTER APPLY per candidate row (2342 rows x 1.1M-row
            -- product_mapping = 55s / timeout; this is ~100x faster).
            supplier_keys AS (
                SELECT DISTINCT ss.store_id, ss.product_code
                FROM {_supplier_stock_source()} ss
                WHERE ss.tenant_id = ?
                  AND ss.supplier_code = ?
                  {store_clause}
                  AND ss.is_active = 1
                  AND ss.product_code IS NOT NULL
            ),
            -- Every OTHER store this supplier's products resolve to, in both
            -- mapping directions, along with that store's own product_code for
            -- the mapping (needed to look up its stock below - codes differ
            -- across stores). Raw (uncast) predicates keep the source/target
            -- product_mapping index seeks sargable.
            map_resolved AS (
                SELECT sk.store_id AS key_store, sk.product_code AS key_code,
                       pm.target_store_id AS other_store, pm.target_product_code AS other_code
                FROM supplier_keys sk
                JOIN dbo.product_mapping pm
                  ON pm.tenant_id = ?
                 AND pm.is_deleted = 0
                 AND pm.status IN ('APPROVED', 'AUTO')
                 AND pm.source_store_id = sk.store_id
                 AND pm.source_product_code = sk.product_code
                 AND pm.target_store_id <> sk.store_id
                UNION
                SELECT sk.store_id, sk.product_code, pm.source_store_id, pm.source_product_code
                FROM supplier_keys sk
                JOIN dbo.product_mapping pm
                  ON pm.tenant_id = ?
                 AND pm.is_deleted = 0
                 AND pm.status IN ('APPROVED', 'AUTO')
                 AND pm.target_store_id = sk.store_id
                 AND pm.target_product_code = sk.product_code
                 AND pm.source_store_id <> sk.store_id
            ),
            -- mapped_other_store_count and other_store_has_stock both aggregate
            -- off map_resolved - computed together in one pass (not as two CTEs
            -- each referencing map_resolved) because SQL Server re-evaluates a
            -- CTE for every reference to it rather than materializing it once;
            -- two references here doubled the product_mapping walk and turned a
            -- ~2s query into ~29s (measured against a 1600-row supplier).
            mapagg AS (
                SELECT mr.key_store, mr.key_code,
                       COUNT(DISTINCT mr.other_store) AS mapped_other_store_count,
                       MAX(CASE WHEN ISNULL(op.totalstock, 0) > 0 THEN 1 ELSE 0 END) AS other_store_has_stock
                FROM map_resolved mr
                LEFT JOIN sync.Products op
                  ON op.tenant_id = ?
                 AND op.store_id = mr.other_store
                 AND op.productcode = TRY_CAST(mr.other_code AS INT)
                GROUP BY mr.key_store, mr.key_code
            )
            SELECT TOP 3000
                ss.supplier_stock_id,
                CAST(ss.tenant_id AS VARCHAR(36)) AS tenant_id,
                CAST(ss.store_id AS VARCHAR(36)) AS store_id,
                st.store_code,
                st.store_name,
                CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                CAST(ss.supplier_product_code AS VARCHAR(100)) AS supplier_product_code,
                ss.supplier_product_name,
                CAST(ss.product_code AS VARCHAR(100)) AS product_code,
                p.productname AS mapped_product_name,
                ss.available_stock,
                ss.ptr,
                ss.mrp,
                ss.discount,
                p.TaxId AS gst,
                ss.packing,
                ss.free,
                ss.minimum_qty,
                ss.scheme,
                ss.transaction_date,
                ss.source,
                ss.imported_at,
                CASE WHEN ss.product_code IS NULL THEN 0 ELSE 1 END AS has_mapping,
                ascnt.total_store_count,
                CASE
                    WHEN ss.product_code IS NULL THEN 0
                    ELSE 1 + ISNULL(mapagg.mapped_other_store_count, 0)
                END AS mapped_store_count,
                CASE
                    WHEN ss.product_code IS NULL THEN ascnt.total_store_count
                    ELSE ascnt.total_store_count - (1 + ISNULL(mapagg.mapped_other_store_count, 0))
                END AS unmapped_store_count,
                CASE
                    WHEN ss.product_code IS NULL THEN 'not_mapped'
                    WHEN ascnt.total_store_count - (1 + ISNULL(mapagg.mapped_other_store_count, 0)) > 0 THEN 'partially_matched'
                    ELSE 'fully_matched'
                END AS mapping_scope_status,
                -- Stock of this row's own store (the selected warehouse, since
                -- this list is always warehouse-scoped via store_id) and whether
                -- any OTHER mapped store carries stock - feeds the stock-status
                -- filter. NULL/no product resolves to 0, matching this module's
                -- existing ISNULL(...,0) stock convention throughout.
                ISNULL(p.totalstock, 0) AS own_store_stock,
                ISNULL(mapagg.other_store_has_stock, 0) AS other_store_has_stock
            FROM {_supplier_stock_source()} ss
            CROSS JOIN active_store_count ascnt
            LEFT JOIN dbo.stores st ON st.tenant_id = ss.tenant_id AND st.store_id = ss.store_id
            -- sync.Products.productcode is INT; convert the varchar supplier code
            -- to INT (TRY_CAST -> NULL, never errors) so the indexed INT column
            -- stays sargable instead of CAST-ing both sides to VARCHAR.
            LEFT JOIN sync.Products p
                ON p.tenant_id = ss.tenant_id
               AND p.store_id = ss.store_id
               AND p.productcode = TRY_CAST(ss.product_code AS INT)
            LEFT JOIN mapagg
                ON mapagg.key_store = ss.store_id
               AND mapagg.key_code = ss.product_code
            WHERE ss.tenant_id = ?
              AND ss.supplier_code = ?
              {store_clause}
              AND ss.is_active = 1
              AND (? = 0 OR ISNULL(ss.available_stock, 0) > 0)
              AND (? = ''
                   OR ss.supplier_product_name LIKE '%' + ? + '%'
                   OR CAST(ss.supplier_product_code AS VARCHAR(100)) LIKE ? + '%'
                   OR CAST(ss.product_code AS VARCHAR(100)) LIKE ? + '%')
            ORDER BY ss.supplier_product_name
            """,
            tuple(params),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def _warehouse_search_clause(search):
    """Shared LIKE predicate + its 3 bound params, reused by both the counts
    and products queries below so their `base` CTEs stay identical."""
    term = (search or "").strip()
    clause = "(? = '' OR p.productname LIKE '%' + ? + '%' OR CAST(p.productcode AS VARCHAR(100)) LIKE ? + '%')"
    return clause, [term, term, term]


def warehouse_stock_counts(tenant_id, store_id):
    """Store-wide (not supplier-scoped) stock-status counts for the NMW Stock
    filter dropdown - authoritative over the WHOLE active catalogue of
    `store_id`, independent of any supplier selection. Cross-store comparison
    (other_store_has_stock) only ever runs against the zero-stock subset
    (zero_base), not the full ~59k-row catalogue, since that's the only
    subset the "Mine=0 + ..." buckets need - keeps the product_mapping walk
    bounded to however many products are actually out of stock, not the
    whole store."""
    search_clause, search_params = _warehouse_search_clause("")
    rows = _fetch(
        f"""
        WITH base AS (
            SELECT CAST(p.productcode AS VARCHAR(100)) AS product_code,
                   ISNULL(p.totalstock, 0) AS own_store_stock
            FROM sync.Products p
            WHERE p.tenant_id = ? AND p.store_id = ? AND ISNULL(p.isactive, 1) = 1
              AND {search_clause}
        ),
        zero_base AS (
            SELECT product_code FROM base WHERE own_store_stock <= 0
        ),
        -- Driven FROM product_mapping (filtered on the fixed store_id, which
        -- is a cheap ~200k-row index-seek range on this store regardless of
        -- catalogue size - see IX_product_mapping_source_seek/target_seek),
        -- not from zero_base out to product_mapping per-row: with a 30k-row
        -- zero-stock set that correlated-seek shape measured 68s (one nested
        -- seek per product); this hash/merge-friendly shape is the fix.
        map_resolved AS (
            SELECT pm.source_product_code AS key_code, pm.target_store_id AS other_store, pm.target_product_code AS other_code
            FROM dbo.product_mapping pm
            WHERE pm.tenant_id = ?
              AND pm.is_deleted = 0
              AND pm.status IN ('APPROVED', 'AUTO')
              AND pm.source_store_id = ?
              AND pm.target_store_id <> ?
            UNION
            SELECT pm.target_product_code, pm.source_store_id, pm.source_product_code
            FROM dbo.product_mapping pm
            WHERE pm.tenant_id = ?
              AND pm.is_deleted = 0
              AND pm.status IN ('APPROVED', 'AUTO')
              AND pm.target_store_id = ?
              AND pm.source_store_id <> ?
        ),
        other_stock AS (
            SELECT mr.key_code, MAX(CASE WHEN ISNULL(op.totalstock, 0) > 0 THEN 1 ELSE 0 END) AS other_store_has_stock
            FROM map_resolved mr
            JOIN zero_base zb ON zb.product_code = mr.key_code
            LEFT JOIN sync.Products op
              ON op.tenant_id = ?
             AND op.store_id = mr.other_store
             AND op.productcode = TRY_CAST(mr.other_code AS INT)
            GROUP BY mr.key_code
        )
        SELECT
            COUNT(1) AS total,
            SUM(CASE WHEN b.own_store_stock <= 0 THEN 1 ELSE 0 END) AS zero,
            SUM(CASE WHEN b.own_store_stock > 0 THEN 1 ELSE 0 END) AS positive,
            SUM(CASE WHEN b.own_store_stock <= 0 AND ISNULL(os.other_store_has_stock, 0) = 1 THEN 1 ELSE 0 END) AS zero_other_positive,
            SUM(CASE WHEN b.own_store_stock <= 0 AND ISNULL(os.other_store_has_stock, 0) = 0 THEN 1 ELSE 0 END) AS zero_all_zero
        FROM base b
        LEFT JOIN other_stock os ON os.key_code = b.product_code
        """,
        (
            tenant_id, store_id, *search_params,
            tenant_id, store_id, store_id,
            tenant_id, store_id, store_id,
            tenant_id,
        ),
    )
    row = rows[0] if rows else {}
    return {
        "all": int(row.get("total") or 0),
        "zero": int(row.get("zero") or 0),
        "positive": int(row.get("positive") or 0),
        "zero_other_positive": int(row.get("zero_other_positive") or 0),
        "zero_all_zero": int(row.get("zero_all_zero") or 0),
    }


def warehouse_stock_products(tenant_id, store_id, stock_filter, search="", limit=3000):
    """The NMW-Stock-filtered product list itself (not supplier-scoped - see
    warehouse_stock_counts). 'zero'/'positive' need no cross-store join at all
    (cheap, capped directly). The 'zero_other_positive'/'zero_all_zero'
    buckets must resolve cross-store stock for every zero-stock product
    BEFORE capping to `limit`, since the cross-store predicate decides which
    rows even qualify - capping first (then joining) could arbitrarily drop
    qualifying rows whose product name happens to sort after row `limit`."""
    search_clause, search_params = _warehouse_search_clause(search)
    base_where = f"p.tenant_id = ? AND p.store_id = ? AND ISNULL(p.isactive, 1) = 1 AND {search_clause}"

    if stock_filter not in ("zero", "positive", "zero_other_positive", "zero_all_zero"):
        return {"items": [], "total_matching": 0}

    if stock_filter in ("zero", "positive"):
        stock_predicate = "ISNULL(p.totalstock, 0) <= 0" if stock_filter == "zero" else "ISNULL(p.totalstock, 0) > 0"
        rows = _fetch(
            f"""
            SELECT TOP (?)
                CAST(p.productcode AS VARCHAR(100)) AS product_code,
                p.productname AS product_name,
                ISNULL(p.totalstock, 0) AS own_store_stock,
                0 AS other_store_has_stock,
                p.saleunit AS sale_unit,
                p.unitdescription AS unit_description,
                p.mrp,
                p.purchaseprice AS ptr,
                COUNT(1) OVER() AS total_matching
            FROM sync.Products p
            WHERE {base_where} AND {stock_predicate}
            ORDER BY p.productname
            """,
            (limit, tenant_id, store_id, *search_params),
        )
    else:
        want_other_stock = 1 if stock_filter == "zero_other_positive" else 0
        rows = _fetch(
            f"""
            WITH base AS (
                SELECT CAST(p.productcode AS VARCHAR(100)) AS product_code,
                       p.productname AS product_name,
                       ISNULL(p.totalstock, 0) AS own_store_stock,
                       p.saleunit AS sale_unit,
                       p.unitdescription AS unit_description,
                       p.mrp,
                       p.purchaseprice AS ptr
                FROM sync.Products p
                WHERE {base_where} AND ISNULL(p.totalstock, 0) <= 0
            ),
            -- Driven FROM product_mapping (see warehouse_stock_counts for why:
            -- a per-row correlated seek from a large zero-stock set measured
            -- 68s; filtering product_mapping on the fixed store_id first and
            -- joining back to base is the fast shape).
            map_resolved AS (
                SELECT pm.source_product_code AS key_code, pm.target_store_id AS other_store, pm.target_product_code AS other_code
                FROM dbo.product_mapping pm
                WHERE pm.tenant_id = ?
                  AND pm.is_deleted = 0
                  AND pm.status IN ('APPROVED', 'AUTO')
                  AND pm.source_store_id = ?
                  AND pm.target_store_id <> ?
                UNION
                SELECT pm.target_product_code, pm.source_store_id, pm.source_product_code
                FROM dbo.product_mapping pm
                WHERE pm.tenant_id = ?
                  AND pm.is_deleted = 0
                  AND pm.status IN ('APPROVED', 'AUTO')
                  AND pm.target_store_id = ?
                  AND pm.source_store_id <> ?
            ),
            other_stock AS (
                SELECT mr.key_code, MAX(CASE WHEN ISNULL(op.totalstock, 0) > 0 THEN 1 ELSE 0 END) AS other_store_has_stock
                FROM map_resolved mr
                JOIN base b ON b.product_code = mr.key_code
                LEFT JOIN sync.Products op
                  ON op.tenant_id = ?
                 AND op.store_id = mr.other_store
                 AND op.productcode = TRY_CAST(mr.other_code AS INT)
                GROUP BY mr.key_code
            ),
            matched AS (
                SELECT b.product_code, b.product_name, b.own_store_stock,
                       ISNULL(os.other_store_has_stock, 0) AS other_store_has_stock,
                       b.sale_unit, b.unit_description, b.mrp, b.ptr
                FROM base b
                LEFT JOIN other_stock os ON os.key_code = b.product_code
                WHERE ISNULL(os.other_store_has_stock, 0) = ?
            )
            SELECT TOP (?) *, COUNT(1) OVER() AS total_matching
            FROM matched
            ORDER BY product_name
            """,
            (
                tenant_id, store_id, *search_params,
                tenant_id, store_id, store_id,
                tenant_id, store_id, store_id,
                tenant_id,
                want_other_stock,
                limit,
            ),
        )

    total_matching = int(rows[0]["total_matching"]) if rows else 0
    for row in rows:
        row.pop("total_matching", None)
    return {"items": rows, "total_matching": total_matching}


def supplier_analysis_report(tenant_id, supplier_code, store_id=None, only_available=False):
    conn = get_connection()
    try:
        cur = conn.cursor()
        store_clause = "AND ss.store_id = ?" if store_id else ""
        params = [tenant_id, tenant_id, supplier_code]
        if store_id:
            params.append(store_id)
        params.append(1 if only_available else 0)
        cur.execute(
            f"""
            WITH active_store_count AS (
                SELECT COUNT(1) AS total_store_count
                FROM dbo.stores
                WHERE tenant_id = ?
                  AND ISNULL(is_active, 1) = 1
            ),
            supplier_rows AS (
                SELECT
                    ss.supplier_stock_id,
                    CAST(ss.tenant_id AS VARCHAR(36)) AS tenant_id,
                    CAST(ss.store_id AS VARCHAR(36)) AS source_store_id,
                    st.store_code AS source_store_code,
                    st.store_name AS source_store_name,
                    CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                    CAST(ss.supplier_product_code AS VARCHAR(100)) AS supplier_product_code,
                    ss.supplier_product_name,
                    ss.product_code AS product_code,
                    p.productname AS mapped_product_name,
                    ISNULL(ss.available_stock, 0) AS supplier_available_stock,
                    ss.ptr,
                    ss.mrp,
                    ascnt.total_store_count
                FROM {_supplier_stock_source()} ss
                CROSS JOIN active_store_count ascnt
                LEFT JOIN dbo.stores st
                  ON st.tenant_id = ss.tenant_id AND st.store_id = ss.store_id
                LEFT JOIN sync.Products p
                  ON p.tenant_id = ss.tenant_id
                 AND p.store_id = ss.store_id
                 AND p.productcode = TRY_CAST(ss.product_code AS INT)
                WHERE ss.tenant_id = ?
                  AND ss.supplier_code = ?
                  {store_clause}
                  AND ss.is_active = 1
                  AND (? = 0 OR ISNULL(ss.available_stock, 0) > 0)
            ),
            resolved_stores AS (
                SELECT
                    sr.supplier_stock_id,
                    sr.source_store_id AS store_id,
                    sr.product_code,
                    'source' AS store_match_status
                FROM supplier_rows sr
                WHERE sr.product_code IS NOT NULL

                UNION

                SELECT
                    sr.supplier_stock_id,
                    CAST(pm.target_store_id AS VARCHAR(36)) AS store_id,
                    CAST(pm.target_product_code AS VARCHAR(100)) AS product_code,
                    'mapped' AS store_match_status
                FROM supplier_rows sr
                JOIN dbo.product_mapping pm
                  ON pm.tenant_id = sr.tenant_id
                 AND pm.is_deleted = 0
                 AND pm.status IN ('APPROVED', 'AUTO')
                 AND pm.source_store_id = sr.source_store_id
                 AND pm.source_product_code = sr.product_code
                 AND pm.target_product_code IS NOT NULL
                WHERE sr.product_code IS NOT NULL

                UNION

                SELECT
                    sr.supplier_stock_id,
                    CAST(pm.source_store_id AS VARCHAR(36)) AS store_id,
                    CAST(pm.source_product_code AS VARCHAR(100)) AS product_code,
                    'mapped' AS store_match_status
                FROM supplier_rows sr
                JOIN dbo.product_mapping pm
                  ON pm.tenant_id = sr.tenant_id
                 AND pm.is_deleted = 0
                 AND pm.status IN ('APPROVED', 'AUTO')
                 AND pm.target_store_id = sr.source_store_id
                 AND pm.target_product_code = sr.product_code
                 AND pm.source_product_code IS NOT NULL
                WHERE sr.product_code IS NOT NULL
            ),
            resolved_stock AS (
                SELECT
                    rs.supplier_stock_id,
                    rs.store_id,
                    rs.product_code,
                    rs.store_match_status,
                    st.store_code,
                    st.store_name,
                    ISNULL(p.totalstock, 0) AS current_stock
                FROM resolved_stores rs
                LEFT JOIN dbo.stores st
                  ON st.tenant_id = ? AND st.store_id = rs.store_id
                LEFT JOIN sync.Products p
                  ON p.tenant_id = ?
                 AND p.store_id = rs.store_id
                 AND p.ProductCode = TRY_CONVERT(INT, rs.product_code)
                 AND ISNULL(p.isactive, 1) = 1
            ),
            recent_movement AS (
                SELECT
                    rs.supplier_stock_id,
                    rs.store_id,
                    SUM(ISNULL(pt.SaleQuantity, 0)) AS recent_sale_qty
                FROM resolved_stores rs
                LEFT JOIN sync.ProductTrans pt
                  ON pt.tenant_id = ?
                 AND pt.store_id = rs.store_id
                 AND pt.ProductCode = TRY_CONVERT(INT, rs.product_code)
                 AND pt.MonthOfStatistics >= DATEADD(MONTH, -3, GETDATE())
                GROUP BY rs.supplier_stock_id, rs.store_id
            )
            SELECT
                sr.supplier_stock_id,
                sr.supplier_code,
                sr.supplier_product_code,
                sr.supplier_product_name,
                sr.product_code,
                sr.mapped_product_name,
                sr.source_store_id,
                sr.source_store_code,
                sr.source_store_name,
                sr.supplier_available_stock,
                sr.ptr,
                sr.mrp,
                sr.total_store_count,
                COUNT(DISTINCT rs.store_id) AS mapped_store_count,
                sr.total_store_count - COUNT(DISTINCT rs.store_id) AS unmapped_store_count,
                COUNT(DISTINCT CASE WHEN ISNULL(stk.current_stock, 0) > 0 THEN rs.store_id END) AS stores_with_stock_count,
                COUNT(DISTINCT CASE WHEN rs.store_id IS NOT NULL AND ISNULL(stk.current_stock, 0) <= 0 THEN rs.store_id END) AS stores_without_stock_count,
                SUM(ISNULL(stk.current_stock, 0)) AS network_stock_qty,
                MAX(CASE WHEN rs.store_id = sr.source_store_id THEN ISNULL(stk.current_stock, 0) ELSE 0 END) AS source_store_stock_qty,
                SUM(ISNULL(mv.recent_sale_qty, 0)) AS recent_3m_sale_qty,
                CAST(SUM(ISNULL(mv.recent_sale_qty, 0)) / 3.0 AS DECIMAL(18, 2)) AS avg_monthly_sale_qty,
                CASE
                    WHEN sr.product_code IS NULL THEN 'not_mapped'
                    WHEN sr.total_store_count - COUNT(DISTINCT rs.store_id) > 0 THEN 'partially_matched'
                    ELSE 'fully_matched'
                END AS mapping_scope_status,
                CASE
                    WHEN sr.product_code IS NULL THEN 'not_mapped_products'
                    WHEN sr.total_store_count - COUNT(DISTINCT rs.store_id) > 0 THEN 'stores_not_mapped'
                    WHEN MAX(CASE WHEN rs.store_id = sr.source_store_id THEN ISNULL(stk.current_stock, 0) ELSE 0 END) <= 0
                         AND SUM(ISNULL(mv.recent_sale_qty, 0)) > 0 THEN 'home_store_no_stock_prediction'
                    WHEN COUNT(DISTINCT CASE WHEN rs.store_id IS NOT NULL AND ISNULL(stk.current_stock, 0) <= 0 THEN rs.store_id END) > 0 THEN 'mapped_store_no_stock'
                    ELSE 'already_mapped'
                END AS analysis_bucket,
                CASE
                    WHEN sr.product_code IS NULL THEN 0
                    WHEN MAX(CASE WHEN rs.store_id = sr.source_store_id THEN ISNULL(stk.current_stock, 0) ELSE 0 END) > 0 THEN 0
                    ELSE CEILING(SUM(ISNULL(mv.recent_sale_qty, 0)) / 3.0)
                END AS predicted_required_qty
            FROM supplier_rows sr
            LEFT JOIN resolved_stores rs
              ON rs.supplier_stock_id = sr.supplier_stock_id
            LEFT JOIN resolved_stock stk
              ON stk.supplier_stock_id = rs.supplier_stock_id
             AND stk.store_id = rs.store_id
             AND stk.product_code = rs.product_code
            LEFT JOIN recent_movement mv
              ON mv.supplier_stock_id = rs.supplier_stock_id
             AND mv.store_id = rs.store_id
            GROUP BY
                sr.supplier_stock_id,
                sr.supplier_code,
                sr.supplier_product_code,
                sr.supplier_product_name,
                sr.product_code,
                sr.mapped_product_name,
                sr.source_store_id,
                sr.source_store_code,
                sr.source_store_name,
                sr.supplier_available_stock,
                sr.ptr,
                sr.mrp,
                sr.total_store_count
            ORDER BY sr.supplier_product_name
            """,
            (*params, tenant_id, tenant_id, tenant_id),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def supplier_stock_row(supplier_stock_id, tenant_id=None):
    try:
        bytes.fromhex(supplier_stock_id or "")
    except ValueError:
        return None
    params = [supplier_stock_id]
    tenant_clause = ""
    if tenant_id:
        tenant_clause = "AND ss.tenant_id = ?"
        params.append(tenant_id)
    rows = _fetch(
        f"""
        SELECT TOP 1
            ss.supplier_stock_id,
            CAST(ss.tenant_id AS VARCHAR(36)) AS tenant_id,
            CAST(ss.store_id AS VARCHAR(36)) AS store_id,
            ss.supplier_code,
            ss.supplier_product_code,
            ss.supplier_product_name,
            ss.product_code,
            ss.available_stock, ss.ptr, ss.mrp, ss.discount, ss.packing, ss.free,
            ss.minimum_qty, ss.scheme
        FROM {_supplier_stock_source()} ss
        WHERE ss.supplier_stock_id = ?
          {tenant_clause}
        """,
        tuple(params),
    )
    return rows[0] if rows else None


def exact_mapping(tenant_id, store_id, supplier_code, supplier_product_code):
    rows = _fetch(
        """
        SELECT TOP 1
            CAST(spm.store_id AS VARCHAR(36)) AS store_id,
            CAST(spm.tenant_id AS VARCHAR(36)) AS tenant_id,
            CAST(spm.SupplierCode AS VARCHAR(100)) AS supplier_code,
            CAST(spm.SupplierProductCode AS VARCHAR(100)) AS supplier_product_code,
            spm.SupplierProductName AS supplier_product_name,
            CAST(spm.ProductCode AS VARCHAR(100)) AS product_code,
            p.productname AS product_name,
            spm.UserName AS username,
            spm.LastModifiedDate AS last_modified_date
        FROM sync.SupplierProductMatch spm
        LEFT JOIN sync.Products p
            ON p.tenant_id = spm.tenant_id
           AND p.store_id = spm.store_id
           AND CAST(p.productcode AS VARCHAR(100)) = CAST(spm.ProductCode AS VARCHAR(100))
        WHERE spm.tenant_id = ?
          AND spm.store_id = ?
          AND CAST(spm.SupplierCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND CAST(spm.SupplierProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND ISNULL(spm.IsActive, 1) = 1
        """,
        (tenant_id, store_id, supplier_code, supplier_product_code),
    )
    return rows[0] if rows else None


def mapped_product(tenant_id, store_id, product_code):
    rows = _fetch(
        """
        SELECT TOP 1
            CAST(p.tenant_id AS VARCHAR(36)) AS tenant_id,
            CAST(p.store_id AS VARCHAR(36)) AS store_id,
            CAST(p.productcode AS VARCHAR(100)) AS product_code,
            p.productname AS product_name
        FROM sync.Products p
        WHERE p.tenant_id = ?
          AND p.store_id = ?
          AND CAST(p.productcode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND ISNULL(p.isactive, 1) = 1
        """,
        (tenant_id, store_id, product_code),
    )
    return rows[0] if rows else None


def list_active_stores(tenant_id):
    return _fetch(
        """
        SELECT
            CAST(store_id AS VARCHAR(36)) AS store_id,
            store_code,
            store_name
        FROM dbo.stores
        WHERE tenant_id = ?
          AND ISNULL(is_active, 1) = 1
        ORDER BY store_name
        """,
        (tenant_id,),
    )


def _resolved_pairs(pairs):
    return [
        (row["store_id"], row["product_code"])
        for row in pairs
        if row.get("product_code") is not None and str(row.get("product_code")).strip().isdigit()
    ]


def all_store_stock(tenant_id, pairs):
    pairs = _resolved_pairs(pairs)
    if not pairs:
        return []
    values = ", ".join(["(CAST(? AS UNIQUEIDENTIFIER), CAST(? AS INT))"] * len(pairs))
    params = []
    for store_id, code in pairs:
        params.extend([store_id, int(code)])
    return _fetch(
        f"""
        WITH target(store_id, product_code) AS (
            SELECT * FROM (VALUES {values}) v(store_id, product_code)
        )
        SELECT
            CAST(st.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            COALESCE(CAST(p.productcode AS VARCHAR(100)), CAST(t.product_code AS VARCHAR(100))) AS product_code,
            p.productname AS product_name,
            ISNULL(p.totalstock, 0) AS total_stock,
            p.saleunit AS sale_unit,
            p.unitdescription AS unit_description,
            p.mrp,
            p.purchaseprice AS ptr,
            MAX(b.grndate) AS last_grn_date,
            MAX(b.lastsaledate) AS last_sale_date
        FROM target t
        JOIN dbo.stores st
          ON st.tenant_id = ? AND st.store_id = t.store_id
        LEFT JOIN sync.Products p
          ON p.tenant_id = ? AND p.store_id = t.store_id
         AND p.ProductCode = t.product_code
         AND ISNULL(p.isactive, 1) = 1
        LEFT JOIN sync.Batches b
          ON b.tenant_id = ? AND b.store_id = t.store_id
         AND b.ProductCode = t.product_code
        GROUP BY st.store_id, st.store_code, st.store_name, p.productcode, t.product_code,
                 p.productname, p.totalstock, p.saleunit, p.unitdescription,
                 p.mrp, p.purchaseprice
        ORDER BY st.store_name
        """,
        (*params, tenant_id, tenant_id, tenant_id),
    )


def batches_all_stores(tenant_id, pairs):
    pairs = _resolved_pairs(pairs)
    if not pairs:
        return []
    values = ", ".join(["(CAST(? AS UNIQUEIDENTIFIER), CAST(? AS INT))"] * len(pairs))
    params = []
    for store_id, code in pairs:
        params.extend([store_id, int(code)])
    return _fetch(
        f"""
        WITH target(store_id, product_code) AS (
            SELECT * FROM (VALUES {values}) v(store_id, product_code)
        ),
        ranked_batches AS (
            SELECT
                CAST(b.store_id AS VARCHAR(36)) AS store_id,
                st.store_code,
                st.store_name,
                CAST(b.productcode AS VARCHAR(100)) AS product_code,
                b.batchcode,
                b.stock,
                b.mrp,
                b.expirydate,
                b.itemcost,
                b.purchaseprice AS ptr,
                b.grndate,
                b.lastsaledate,
                ROW_NUMBER() OVER (
                    PARTITION BY b.store_id
                    ORDER BY
                        CASE WHEN ISNULL(b.stock, 0) > 0 THEN 0 ELSE 1 END,
                        b.grndate DESC,
                        b.expirydate DESC,
                        b.batchcode DESC
                ) AS rn
            FROM target t
            JOIN sync.Batches b
              ON b.store_id = t.store_id AND b.ProductCode = t.product_code
            LEFT JOIN dbo.stores st ON st.tenant_id = b.tenant_id AND st.store_id = b.store_id
            WHERE b.tenant_id = ?
              AND ISNULL(b.stock, 0) >= 0
        )
        SELECT
            store_id,
            store_code,
            store_name,
            product_code,
            batchcode,
            stock,
            mrp,
            expirydate,
            itemcost,
            ptr,
            grndate,
            lastsaledate
        FROM ranked_batches
        WHERE rn <= 50
        ORDER BY store_name, rn
        """,
        (*params, tenant_id),
    )


def purchase_history_all_stores(tenant_id, pairs):
    pairs = _resolved_pairs(pairs)
    if not pairs:
        return []
    values = ", ".join(["(CAST(? AS UNIQUEIDENTIFIER), CAST(? AS INT))"] * len(pairs))
    params = []
    for store_id, code in pairs:
        params.extend([store_id, int(code)])
    return _fetch(
        f"""
        WITH target(store_id, product_code) AS (
            SELECT * FROM (VALUES {values}) v(store_id, product_code)
        ),
        ranked_purchases AS (
            SELECT
                CAST(pt.store_id AS VARCHAR(36)) AS store_id,
                st.store_code,
                st.store_name,
                pt.Grnnumber AS grn_no,
                pt.stockreceived AS qty,
                pt.FreeQty AS free,
                pt.DiscountAmount AS overall_discount,
                pt.ProductDiscPercent AS discount,
                pt.itemcost,
                pt.purchaseprice AS ptr,
                pt.mrp,
                pt.grndate,
                COALESCE(s.suppliername, CAST(pt.SupplierCode AS NVARCHAR(100))) AS supplier,
                ROW_NUMBER() OVER (
                    PARTITION BY pt.store_id
                    ORDER BY pt.grndate DESC, pt.Grnnumber DESC
                ) AS rn
            FROM target t
            JOIN sync.PurchaseTrans pt
              ON pt.store_id = t.store_id AND pt.ProductCode = t.product_code
            LEFT JOIN dbo.stores st ON st.tenant_id = pt.tenant_id AND st.store_id = pt.store_id
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = pt.tenant_id
               AND s.store_id = pt.store_id
               AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
            WHERE pt.tenant_id = ?
        )
        SELECT
            store_id,
            store_code,
            store_name,
            grn_no,
            qty,
            free,
            overall_discount,
            discount,
            itemcost,
            ptr,
            mrp,
            grndate,
            supplier
        FROM ranked_purchases
        WHERE rn <= 50
        ORDER BY grndate DESC
        """,
        (*params, tenant_id),
    )


def sales_history_all_stores(tenant_id, pairs):
    pairs = _resolved_pairs(pairs)
    if not pairs:
        return []
    values = ", ".join(["(CAST(? AS UNIQUEIDENTIFIER), CAST(? AS INT))"] * len(pairs))
    params = []
    for store_id, code in pairs:
        params.extend([store_id, int(code)])
    return _fetch(
        f"""
        WITH target(store_id, product_code) AS (
            SELECT * FROM (VALUES {values}) v(store_id, product_code)
        ),
        sales_grouped AS (
            SELECT
                CAST(psi.store_id AS VARCHAR(36)) AS store_id,
                st.store_code,
                st.store_name,
                psi.BillNumber AS bill_no,
                si.BillDate AS bill_date,
                SUM(psi.quantity) AS qty,
                MAX(psi.DiscountPercentage) AS discount,
                psi.Seriesname AS bill_type,
                psi.mrp,
                psi.purchaseprice AS ptr,
                si.CUSTOMERNAME AS customer_name
            FROM target t
            JOIN sync.ProductSaleInformation psi
              ON psi.store_id = t.store_id AND psi.ProductCode = t.product_code
            LEFT JOIN dbo.stores st ON st.tenant_id = psi.tenant_id AND st.store_id = psi.store_id
            LEFT JOIN sync.SaleInformation si
                ON si.tenant_id = psi.tenant_id
               AND si.store_id = psi.store_id
               AND si.billnumber = psi.BillNumber
            WHERE psi.tenant_id = ?
              AND ISNULL(psi.transactionvalidity, 0) = 0
            GROUP BY psi.store_id, st.store_code, st.store_name, psi.BillNumber,
                     si.BillDate, psi.Seriesname, psi.mrp, psi.purchaseprice, si.CUSTOMERNAME
        ),
        ranked_sales AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY store_id
                       ORDER BY bill_date DESC, bill_no DESC
                   ) AS rn
            FROM sales_grouped
        )
        SELECT
            store_id,
            store_code,
            store_name,
            bill_no,
            bill_date,
            qty,
            discount,
            bill_type,
            mrp,
            ptr,
            customer_name
        FROM ranked_sales
        WHERE rn <= 50
        ORDER BY bill_date DESC
        """,
        (*params, tenant_id),
    )


def monthly_movement_all_stores(tenant_id, pairs, months=6):
    pairs = _resolved_pairs(pairs)
    if not pairs:
        return []
    values = ", ".join(["(CAST(? AS UNIQUEIDENTIFIER), CAST(? AS INT))"] * len(pairs))
    params = []
    for store_id, code in pairs:
        params.extend([store_id, int(code)])
    return _fetch(
        f"""
        WITH target(store_id, product_code) AS (
            SELECT * FROM (VALUES {values}) v(store_id, product_code)
        )
        SELECT
            CAST(pt.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120) AS month,
            SUM(ISNULL(pt.StockInHand, 0)) AS stock,
            SUM(ISNULL(pt.PurchaseQuantity, 0)) AS purchase_qty,
            SUM(ISNULL(pt.TransferInQuantity, 0)) AS transfer_in_qty,
            SUM(ISNULL(pt.SaleQuantity, 0)) AS sale_qty,
            SUM(ISNULL(pt.TransferOutQuantity, 0)) AS transfer_out_qty,
            SUM(ISNULL(pt.AdjustmentQuantity, 0)) AS adjustment_qty
        FROM target t
        JOIN sync.ProductTrans pt
          ON pt.store_id = t.store_id AND pt.ProductCode = t.product_code
        LEFT JOIN dbo.stores st ON st.tenant_id = pt.tenant_id AND st.store_id = pt.store_id
        WHERE pt.tenant_id = ?
          AND pt.MonthOfStatistics >= DATEADD(MONTH, -?, GETDATE())
        GROUP BY pt.store_id, st.store_code, st.store_name, CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120)
        ORDER BY st.store_name, month
        """,
        (*params, tenant_id, months),
    )


def upsert_mapping(payload):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF EXISTS (
                SELECT 1 FROM sync.SupplierProductMatch
                WHERE tenant_id = ? AND store_id = ?
                  AND CAST(SupplierCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
                  AND CAST(SupplierProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
            )
                UPDATE sync.SupplierProductMatch
                   SET SupplierProductName = ?,
                       ProductCode = ?,
                       UserName = ?,
                       LastModifiedDate = GETDATE(),
                       IsActive = 1
                 WHERE tenant_id = ? AND store_id = ?
                   AND CAST(SupplierCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
                   AND CAST(SupplierProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
            ELSE
                INSERT INTO sync.SupplierProductMatch
                    (store_id, tenant_id, SupplierCode, SupplierProductCode,
                     SupplierProductName, ProductCode, UserName, LastModifiedDate, IsActive)
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), 1)
            """,
            (
                payload["tenant_id"], payload["store_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload.get("supplier_product_name"), payload["product_code"], payload.get("username"),
                payload["tenant_id"], payload["store_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload["store_id"], payload["tenant_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload.get("supplier_product_name"), payload["product_code"], payload.get("username"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    _upsert_ordernmc_match(payload)
    return {"success": True}


def _upsert_ordernmc_match(payload):
    """Mirror a manual mapping into the store's OrderNMC.SupplierProductMatch
    -- the table supplier stock rows resolve their ProductCode through (see
    _supplier_stock_source), and what the legacy order screens join on."""
    store_code = _store_code(payload["tenant_id"], payload["store_id"])
    if not store_code:
        return
    key = (store_code, str(payload["supplier_code"]), str(payload["supplier_product_code"]))
    name = payload.get("supplier_product_name") or None
    user = payload.get("username") or None
    with legacy_database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE SupplierProductMatch SET ProductCode = ?, SupplierProductName = ?, "
            "UserName = ?, LastModifiedDate = GETDATE(), IsActive = 1 "
            "WHERE StoreName = ? AND SupplierCode = ? AND SupplierProductCode = ?",
            (payload["product_code"], name, user, *key),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO SupplierProductMatch (StoreName, SupplierCode, SupplierProductCode, "
                "SupplierProductName, ProductCode, UserName, LastModifiedDate, IsActive) "
                "VALUES (?, ?, ?, ?, ?, ?, GETDATE(), 1)",
                (*key, name, payload["product_code"], user),
            )
        conn.commit()


# OrderNMC.SupplierStock column widths: text columns varchar(50), sch/free/
# minqty int, mrp/ptr decimal(10,2).
_TEXT_MAX = 50


def _text(value):
    text = "" if value is None else str(value).strip()
    return text[:_TEXT_MAX] or None


def _money(value):
    try:
        return None if value is None else round(float(value), 2)
    except (TypeError, ValueError):
        return None


def replace_supplier_stock(tenant_id, store_id, supplier_code, rows, imported_by=None):
    """REPLACE this supplier's rows for the store in OrderNMC.SupplierStock
    (storename = store code) -- the same delete+reinsert the legacy Excel
    import did. A row's Rack is carried forward when the file has none, so a
    re-upload doesn't wipe racks already on file."""
    store_code = _store_code(tenant_id, store_id)
    if not store_code:
        raise ValueError("Unknown store for this tenant.")
    supplier_code = str(supplier_code).strip()
    with legacy_database.get_central_connection() as conn:
        cur = conn.cursor()
        existing_racks = {
            str(r.supplierproductcode): r.Rack
            for r in cur.execute(
                "SELECT supplierproductcode, Rack FROM SupplierStock "
                "WHERE storename = ? AND suppliercode = ?",
                (store_code, supplier_code),
            ).fetchall()
            if r.Rack
        }
        cur.execute(
            "DELETE FROM SupplierStock WHERE storename = ? AND suppliercode = ?",
            (store_code, supplier_code),
        )
        if rows:
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO SupplierStock "
                "(suppliercode, supplierproductcode, supplierproductname, mrp, ptr, "
                "stock, discound, packing, storename, sch, free, transactiondate, minqty, Rack) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?)",
                [
                    (
                        supplier_code, _text(r["supplier_product_code"]),
                        _text(r.get("supplier_product_name")),
                        _money(r.get("mrp")), _money(r.get("ptr")),
                        r.get("available_stock") or 0, _text(r.get("discount")),
                        _text(r.get("packing")), store_code,
                        r.get("scheme") or 0, r.get("free") or 0, r.get("minimum_qty"),
                        _text(r.get("rack")) or existing_racks.get(_text(r["supplier_product_code"])),
                    )
                    for r in rows
                ],
            )
        resolved = cur.execute(
            "SELECT COUNT(1) FROM SupplierStock ss "
            "JOIN SupplierProductMatch spm ON spm.StoreName = ss.storename "
            " AND spm.SupplierCode = ss.suppliercode AND spm.SupplierProductCode = ss.supplierproductcode "
            "WHERE ss.storename = ? AND ss.suppliercode = ?",
            (store_code, supplier_code),
        ).fetchone()[0]
        conn.commit()
    return {"imported": len(rows), "product_codes_resolved": resolved, "store_code": store_code}


def saved_excel_mapping(tenant_id, store_id, supplier_code):
    """The supplier's saved column mapping from OrderNMC.SupplierExcelMapping
    as {excel header: legacy column name} (legacy names, e.g. 'stock')."""
    store_code = _store_code(tenant_id, store_id)
    if not store_code or not supplier_code:
        return {}
    with legacy_database.get_central_connection() as conn:
        rows = conn.cursor().execute(
            "SELECT SupplierColumnName, ColumnName FROM SupplierExcelMapping "
            "WHERE StoreName = ? AND SupplierCode = ?",
            (store_code, str(supplier_code).strip()),
        ).fetchall()
    return {str(r.SupplierColumnName).strip(): str(r.ColumnName).strip() for r in rows if r.SupplierColumnName}


def save_excel_mapping(tenant_id, store_id, supplier_code, columns):
    """Replace the supplier's saved mapping: columns = {excel header: legacy column}."""
    store_code = _store_code(tenant_id, store_id)
    if not store_code:
        return
    supplier_code = str(supplier_code).strip()
    with legacy_database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM SupplierExcelMapping WHERE StoreName = ? AND SupplierCode = ?",
            (store_code, supplier_code),
        )
        for header, column in columns.items():
            cur.execute(
                "INSERT INTO SupplierExcelMapping (SupplierCode, SupplierColumnName, ColumnName, StoreName) "
                "VALUES (?, ?, ?, ?)",
                (supplier_code, str(header)[:100], column, store_code),
            )
        conn.commit()
