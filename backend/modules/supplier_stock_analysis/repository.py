"""Platform-only data access for Supplier Stock Analysis."""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts


def _object_exists(cur, name):
    cur.execute("SELECT OBJECT_ID(?)", (name,))
    row = cur.fetchone()
    return bool(row and row[0])


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
        if not _object_exists(cur, "procurement.supplier_stock"):
            return []
        store_clause = "AND ss.store_id = ?" if store_id else ""
        params = [tenant_id]
        if store_id:
            params.append(store_id)
        term = (search or "").strip()
        params.extend([term, term, term])
        cur.execute(
            f"""
            SELECT
                CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                COALESCE(MAX(NULLIF(s.suppliername, '')), '') AS supplier_name,
                COUNT(1) AS product_count,
                SUM(CASE WHEN ISNULL(ss.available_stock, 0) > 0 THEN 1 ELSE 0 END) AS available_count,
                SUM(ISNULL(ss.available_stock, 0)) AS total_available_stock,
                MAX(ss.imported_at) AS last_imported_at
            FROM procurement.supplier_stock ss
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ss.tenant_id
               AND s.store_id = ss.store_id
               AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(ss.supplier_code AS VARCHAR(100))
            WHERE ss.tenant_id = ?
              {store_clause}
              AND ss.is_active = 1
              AND (? = ''
                   OR CAST(ss.supplier_code AS VARCHAR(100)) LIKE ? + '%'
                   OR s.suppliername LIKE '%' + ? + '%')
            GROUP BY ss.supplier_code
            ORDER BY supplier_name, ss.supplier_code
            """,
            tuple(params),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def list_supplier_products(tenant_id, supplier_code, store_id=None, search="", only_available=True):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not _object_exists(cur, "procurement.supplier_stock"):
            return []
        store_clause = "AND ss.store_id = ?" if store_id else ""
        params = [tenant_id, tenant_id, supplier_code]
        if store_id:
            params.append(store_id)
        term = (search or "").strip()
        params.extend([1 if only_available else 0, term, term, term, term])
        cur.execute(
            f"""
            WITH active_store_count AS (
                SELECT COUNT(1) AS total_store_count
                FROM dbo.stores
                WHERE tenant_id = ?
                  AND ISNULL(is_active, 1) = 1
            )
            SELECT TOP 3000
                CAST(ss.supplier_stock_id AS VARCHAR(36)) AS supplier_stock_id,
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
                    ELSE 1 + ISNULL(mapstats.mapped_other_store_count, 0)
                END AS mapped_store_count,
                CASE
                    WHEN ss.product_code IS NULL THEN ascnt.total_store_count
                    ELSE ascnt.total_store_count - (1 + ISNULL(mapstats.mapped_other_store_count, 0))
                END AS unmapped_store_count,
                CASE
                    WHEN ss.product_code IS NULL THEN 'not_mapped'
                    WHEN ascnt.total_store_count - (1 + ISNULL(mapstats.mapped_other_store_count, 0)) > 0 THEN 'partially_matched'
                    ELSE 'fully_matched'
                END AS mapping_scope_status
            FROM procurement.supplier_stock ss
            CROSS JOIN active_store_count ascnt
            LEFT JOIN dbo.stores st ON st.tenant_id = ss.tenant_id AND st.store_id = ss.store_id
            LEFT JOIN sync.Products p
                ON p.tenant_id = ss.tenant_id
               AND p.store_id = ss.store_id
               AND CAST(p.productcode AS VARCHAR(100)) = CAST(ss.product_code AS VARCHAR(100))
            OUTER APPLY (
                SELECT COUNT(DISTINCT resolved.store_id) AS mapped_other_store_count
                FROM (
                    SELECT CAST(pm.target_store_id AS VARCHAR(36)) AS store_id
                    FROM dbo.product_mapping pm
                    WHERE pm.tenant_id = ss.tenant_id
                      AND pm.is_deleted = 0
                      AND pm.status IN ('APPROVED', 'AUTO')
                      AND pm.source_store_id = ss.store_id
                      -- product_code / source|target_product_code are all
                      -- varchar(50) with the same collation: compare raw so the
                      -- index seeks fire (UX_product_mapping_source_target for the
                      -- source side, IX_product_mapping_target_code for the target
                      -- side). CAST-ing to VARCHAR(100) makes the indexed column
                      -- non-sargable and forces a full scan of the 1.1M-row
                      -- product_mapping table per candidate row -> 45s timeout.
                      AND pm.source_product_code = ss.product_code
                      AND pm.target_store_id <> ss.store_id
                    UNION
                    SELECT CAST(pm.source_store_id AS VARCHAR(36)) AS store_id
                    FROM dbo.product_mapping pm
                    WHERE pm.tenant_id = ss.tenant_id
                      AND pm.is_deleted = 0
                      AND pm.status IN ('APPROVED', 'AUTO')
                      AND pm.target_store_id = ss.store_id
                      AND pm.target_product_code = ss.product_code
                      AND pm.source_store_id <> ss.store_id
                ) resolved
            ) mapstats
            WHERE ss.tenant_id = ?
              AND CAST(ss.supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
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


def supplier_analysis_report(tenant_id, supplier_code, store_id=None, only_available=False):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not _object_exists(cur, "procurement.supplier_stock"):
            return []
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
                    CAST(ss.supplier_stock_id AS VARCHAR(36)) AS supplier_stock_id,
                    CAST(ss.tenant_id AS VARCHAR(36)) AS tenant_id,
                    CAST(ss.store_id AS VARCHAR(36)) AS source_store_id,
                    st.store_code AS source_store_code,
                    st.store_name AS source_store_name,
                    CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                    CAST(ss.supplier_product_code AS VARCHAR(100)) AS supplier_product_code,
                    ss.supplier_product_name,
                    CAST(ss.product_code AS VARCHAR(100)) AS product_code,
                    p.productname AS mapped_product_name,
                    ISNULL(ss.available_stock, 0) AS supplier_available_stock,
                    ss.ptr,
                    ss.mrp,
                    ascnt.total_store_count
                FROM procurement.supplier_stock ss
                CROSS JOIN active_store_count ascnt
                LEFT JOIN dbo.stores st
                  ON st.tenant_id = ss.tenant_id AND st.store_id = ss.store_id
                LEFT JOIN sync.Products p
                  ON p.tenant_id = ss.tenant_id
                 AND p.store_id = ss.store_id
                 AND CAST(p.productcode AS VARCHAR(100)) = CAST(ss.product_code AS VARCHAR(100))
                WHERE ss.tenant_id = ?
                  AND CAST(ss.supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
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
                 AND CAST(pm.source_product_code AS VARCHAR(100)) = CAST(sr.product_code AS VARCHAR(100))
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
                 AND CAST(pm.target_product_code AS VARCHAR(100)) = CAST(sr.product_code AS VARCHAR(100))
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
    params = [supplier_stock_id]
    tenant_clause = ""
    if tenant_id:
        tenant_clause = "AND tenant_id = ?"
        params.append(tenant_id)
    rows = _fetch(
        f"""
        SELECT TOP 1
            CAST(supplier_stock_id AS VARCHAR(36)) AS supplier_stock_id,
            CAST(tenant_id AS VARCHAR(36)) AS tenant_id,
            CAST(store_id AS VARCHAR(36)) AS store_id,
            CAST(supplier_code AS VARCHAR(100)) AS supplier_code,
            CAST(supplier_product_code AS VARCHAR(100)) AS supplier_product_code,
            supplier_product_name,
            CAST(product_code AS VARCHAR(100)) AS product_code,
            available_stock, ptr, mrp, discount, packing, free, minimum_qty, scheme
        FROM procurement.supplier_stock
        WHERE supplier_stock_id = ?
          {tenant_clause}
          AND is_active = 1
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

            UPDATE procurement.supplier_stock
               SET product_code = ?
             WHERE tenant_id = ?
               AND store_id = ?
               AND CAST(supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
               AND CAST(supplier_product_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
               AND is_active = 1
            """,
            (
                payload["tenant_id"], payload["store_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload.get("supplier_product_name"), payload["product_code"], payload.get("username"),
                payload["tenant_id"], payload["store_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload["store_id"], payload["tenant_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload.get("supplier_product_name"), payload["product_code"], payload.get("username"),
                payload["product_code"], payload["tenant_id"], payload["store_id"],
                payload["supplier_code"], payload["supplier_product_code"],
            ),
        )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def replace_supplier_stock(tenant_id, store_id, supplier_code, rows, imported_by):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE procurement.supplier_stock
               SET is_active = 0
             WHERE tenant_id = ? AND store_id = ? AND supplier_code = ? AND source = 'excel'
            """,
            (tenant_id, store_id, supplier_code),
        )
        if rows:
            cur.fast_executemany = True
            cur.executemany(
                """
                INSERT INTO procurement.supplier_stock
                    (tenant_id, store_id, supplier_code, supplier_product_code,
                     supplier_product_name, available_stock, ptr, mrp, discount,
                     packing, free, minimum_qty, scheme, transaction_date, source,
                     is_active, imported_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel', 1, ?)
                """,
                [
                    (
                        tenant_id, store_id, supplier_code,
                        r.get("supplier_product_code"), r.get("supplier_product_name"),
                        r.get("available_stock"), r.get("ptr"), r.get("mrp"),
                        r.get("discount"), r.get("packing"), r.get("free"),
                        r.get("minimum_qty"), r.get("scheme"), r.get("transaction_date"),
                        imported_by,
                    )
                    for r in rows
                ],
            )
        cur.execute(
            """
            UPDATE ss
               SET ss.product_code = CAST(spm.ProductCode AS VARCHAR(50))
            FROM procurement.supplier_stock ss
            JOIN sync.SupplierProductMatch spm
              ON spm.tenant_id = ss.tenant_id
             AND spm.store_id = ss.store_id
             AND CAST(spm.SupplierCode AS VARCHAR(100)) = CAST(ss.supplier_code AS VARCHAR(100))
             AND CAST(spm.SupplierProductCode AS VARCHAR(100)) = CAST(ss.supplier_product_code AS VARCHAR(100))
             AND ISNULL(spm.IsActive, 1) = 1
            WHERE ss.tenant_id = ?
              AND ss.store_id = ?
              AND CAST(ss.supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
              AND ss.source = 'excel'
              AND ss.is_active = 1
            """,
            (tenant_id, store_id, supplier_code),
        )
        resolved = cur.rowcount
        conn.commit()
        return {"imported": len(rows), "product_codes_resolved": resolved}
    finally:
        conn.close()

