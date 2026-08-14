from config.database import get_connection


def _fetch_all(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            for key, value in list(row.items()):
                if hasattr(value, "isoformat"):
                    row[key] = value.isoformat()
        return rows
    finally:
        cursor.close()
        conn.close()


def _fetch_one(sql, params=()):
    rows = _fetch_all(sql, params)
    return rows[0] if rows else None


def search_products(
    tenant_id,
    store_id,
    q,
    starts_with,
    unit_description,
    box_number,
    stock_filter,
    only_null_sublocation,
    only_sale_unit_gt_one,
):
    rows = _fetch_all(
        """
        ;WITH ProductAgg AS (
            SELECT
                b.ProductCode,
                DATEDIFF(DAY, MAX(b.GrnDate), GETDATE()) AS purchase_days,
                DATEDIFF(DAY, MAX(b.LastSaleDate), GETDATE()) AS sale_days,
                SUM(CASE WHEN ISNULL(b.Stock, 0) > 0 THEN ISNULL(b.Stock, 0) ELSE 0 END) AS live_batch_stock
            FROM sync.Batches b
            WHERE b.tenant_id = ?
              AND b.store_id = ?
            GROUP BY b.ProductCode
        )
        SELECT TOP 400
            CAST(p.ProductCode AS NVARCHAR(50)) AS product_code,
            p.ProductName AS product_name,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.UnitDescription)), ''), '') AS NVARCHAR(100)) AS unit_description,
            CAST(ISNULL(p.SaleUnit, 0) AS DECIMAL(18, 2)) AS sale_unit,
            CAST(ISNULL(p.MRP, 0) AS DECIMAL(18, 2)) AS mrp,
            CAST(ISNULL(p.TotalStock, 0) AS DECIMAL(18, 2)) AS total_stock,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.SubLocation)), ''), '') AS NVARCHAR(50)) AS current_sublocation,
            CAST(ISNULL(agg.purchase_days, 0) AS INT) AS purchase_days,
            CAST(ISNULL(agg.sale_days, 0) AS INT) AS sale_days,
            CAST(ISNULL(agg.live_batch_stock, 0) AS DECIMAL(18, 2)) AS batch_stock
        FROM sync.Products p
        LEFT JOIN ProductAgg agg
            ON agg.ProductCode = p.ProductCode
        WHERE p.tenant_id = ?
          AND p.store_id = ?
          AND ISNULL(p.isactive, 1) = 1
          AND (
                ? = ''
                OR p.ProductName LIKE '%' + ? + '%'
                OR CAST(p.ProductCode AS NVARCHAR(50)) LIKE '%' + ? + '%'
              )
          AND (
                ? = ''
                OR p.ProductName LIKE ? + '%'
              )
          AND (
                ? = ''
                OR ISNULL(p.UnitDescription, '') LIKE '%' + ? + '%'
              )
          AND (
                ? = ''
                OR ISNULL(LTRIM(RTRIM(p.SubLocation)), '') = ?
              )
          AND (
                ? = 0
                OR ? <> ''
                OR ISNULL(LTRIM(RTRIM(p.SubLocation)), '') = ''
              )
          AND (
                ? = 0
                OR TRY_CAST(p.SaleUnit AS DECIMAL(18, 2)) > 1
              )
          AND (
                (
                    ? = 'all'
                    AND (
                        ISNULL(p.TotalStock, 0) > 0
                        OR (
                            ISNULL(p.TotalStock, 0) = 0
                            AND agg.sale_days IS NOT NULL
                            AND agg.sale_days <= 90
                        )
                    )
                )
                OR (
                    ? = 'in_stock'
                    AND ISNULL(p.TotalStock, 0) > 0
                )
                OR (
                    ? = 'zero_recent_sale'
                    AND ISNULL(p.TotalStock, 0) = 0
                    AND agg.sale_days IS NOT NULL
                    AND agg.sale_days <= 90
                )
              )
        ORDER BY
            CASE WHEN ISNULL(LTRIM(RTRIM(p.SubLocation)), '') = '' THEN 0 ELSE 1 END,
            ISNULL(LTRIM(RTRIM(p.SubLocation)), ''),
            p.ProductName
        """,
        (
            tenant_id,
            store_id,
            tenant_id,
            store_id,
            q,
            q,
            q,
            starts_with,
            starts_with,
            unit_description,
            unit_description,
            box_number,
            box_number,
            1 if only_null_sublocation else 0,
            box_number,
            1 if only_sale_unit_gt_one else 0,
            stock_filter,
            stock_filter,
            stock_filter,
        ),
    )
    suggestion = _fetch_one(
        """
        SELECT TOP 1
            CAST(LTRIM(RTRIM(SubLocation)) AS NVARCHAR(50)) AS last_box
        FROM sync.Products
        WHERE tenant_id = ?
          AND store_id = ?
          AND ? <> ''
          AND SubLocation IS NOT NULL
          AND LTRIM(RTRIM(SubLocation)) LIKE ? + '%'
        ORDER BY LTRIM(RTRIM(SubLocation)) DESC
        """,
        (tenant_id, store_id, starts_with, starts_with),
    )
    return {
        "rows": rows,
        "last_box_for_letter": (suggestion or {}).get("last_box"),
    }


def get_unit_descriptions(tenant_id, store_id, starts_with):
    rows = _fetch_all(
        """
        SELECT DISTINCT TOP 100
            CAST(LTRIM(RTRIM(UnitDescription)) AS NVARCHAR(100)) AS unit_description
        FROM sync.Products
        WHERE tenant_id = ?
          AND store_id = ?
          AND ISNULL(isactive, 1) = 1
          AND LTRIM(RTRIM(ISNULL(UnitDescription, ''))) <> ''
          AND (? = '' OR ProductName LIKE ? + '%')
        ORDER BY CAST(LTRIM(RTRIM(UnitDescription)) AS NVARCHAR(100))
        """,
        (tenant_id, store_id, starts_with, starts_with),
    )
    return [row["unit_description"] for row in rows if row.get("unit_description")]


def search_boxes(tenant_id, store_id, q, starts_with):
    return _fetch_all(
        """
        ;WITH ProductAgg AS (
            SELECT
                b.ProductCode,
                DATEDIFF(DAY, MAX(b.GrnDate), GETDATE()) AS purchase_days,
                DATEDIFF(DAY, MAX(b.LastSaleDate), GETDATE()) AS sale_days
            FROM sync.Batches b
            WHERE b.tenant_id = ?
              AND b.store_id = ?
            GROUP BY b.ProductCode
        )
        SELECT TOP 200
            CAST(LTRIM(RTRIM(p.SubLocation)) AS NVARCHAR(50)) AS box_number,
            COUNT(*) AS product_count,
            CAST(SUM(ISNULL(p.TotalStock, 0)) AS DECIMAL(18, 2)) AS total_stock,
            CAST(MIN(ISNULL(agg.sale_days, 0)) AS INT) AS best_sale_days,
            CAST(MIN(ISNULL(agg.purchase_days, 0)) AS INT) AS best_purchase_days
        FROM sync.Products p
        LEFT JOIN ProductAgg agg
            ON agg.ProductCode = p.ProductCode
        WHERE p.tenant_id = ?
          AND p.store_id = ?
          AND p.SubLocation IS NOT NULL
          AND LTRIM(RTRIM(p.SubLocation)) <> ''
          AND (? = '' OR LTRIM(RTRIM(p.SubLocation)) LIKE ? + '%')
          AND (? = '' OR LTRIM(RTRIM(p.SubLocation)) = ?)
        GROUP BY LTRIM(RTRIM(p.SubLocation))
        ORDER BY LTRIM(RTRIM(p.SubLocation))
        """,
        (
            tenant_id,
            store_id,
            tenant_id,
            store_id,
            starts_with,
            starts_with,
            q,
            q,
        ),
    )


def get_box_products(tenant_id, store_id, box_number):
    return _fetch_all(
        """
        ;WITH ProductAgg AS (
            SELECT
                b.ProductCode,
                DATEDIFF(DAY, MAX(b.GrnDate), GETDATE()) AS purchase_days,
                DATEDIFF(DAY, MAX(b.LastSaleDate), GETDATE()) AS sale_days
            FROM sync.Batches b
            WHERE b.tenant_id = ?
              AND b.store_id = ?
            GROUP BY b.ProductCode
        )
        SELECT
            CAST(p.ProductCode AS NVARCHAR(50)) AS product_code,
            p.ProductName AS product_name,
            CAST(ISNULL(p.TotalStock, 0) AS DECIMAL(18, 2)) AS total_stock,
            CAST(ISNULL(agg.sale_days, 0) AS INT) AS sale_days,
            CAST(ISNULL(agg.purchase_days, 0) AS INT) AS purchase_days,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.UnitDescription)), ''), '') AS NVARCHAR(100)) AS unit_description,
            CAST(ISNULL(p.SaleUnit, 0) AS DECIMAL(18, 2)) AS sale_unit,
            CAST(ISNULL(p.MRP, 0) AS DECIMAL(18, 2)) AS mrp
        FROM sync.Products p
        LEFT JOIN ProductAgg agg
            ON agg.ProductCode = p.ProductCode
        WHERE p.tenant_id = ?
          AND p.store_id = ?
          AND LTRIM(RTRIM(ISNULL(p.SubLocation, ''))) = ?
        ORDER BY p.ProductName
        """,
        (tenant_id, store_id, tenant_id, store_id, box_number),
    )


def get_product_batches(tenant_id, store_id, product_code):
    has_live_stock = _fetch_one(
        """
        SELECT TOP 1 1 AS has_stock
        FROM sync.Batches
        WHERE tenant_id = ?
          AND store_id = ?
          AND ProductCode = ?
          AND ISNULL(Stock, 0) > 0
        """,
        (tenant_id, store_id, product_code),
    )
    top_clause = "" if has_live_stock else "TOP 5"
    return _fetch_all(
        f"""
        SELECT {top_clause}
            CAST(b.ProductCode AS NVARCHAR(50)) AS product_code,
            CAST(ISNULL(b.BatchCode, '') AS NVARCHAR(50)) AS batch_code,
            CAST(ISNULL(b.Stock, 0) AS DECIMAL(18, 2)) AS stock,
            CAST(b.ExpiryDate AS DATE) AS expiry_date,
            CAST(ISNULL(b.MRP, 0) AS DECIMAL(18, 2)) AS mrp,
            CAST(DATEDIFF(DAY, b.GrnDate, GETDATE()) AS INT) AS purchase_days,
            CAST(DATEDIFF(DAY, b.LastSaleDate, GETDATE()) AS INT) AS sale_days,
            CAST(
                CASE
                    WHEN b.ExpiryDate IS NOT NULL AND CAST(b.ExpiryDate AS DATE) < CAST(GETDATE() AS DATE) THEN 1
                    ELSE 0
                END AS BIT
            ) AS is_expired
        FROM sync.Batches b
        WHERE b.tenant_id = ?
          AND b.store_id = ?
          AND b.ProductCode = ?
          AND ({1 if has_live_stock else 0} = 0 OR ISNULL(b.Stock, 0) > 0)
        ORDER BY
            CASE WHEN ISNULL(b.Stock, 0) > 0 THEN 0 ELSE 1 END,
            b.ExpiryDate,
            b.GrnDate DESC
        """,
        (tenant_id, store_id, product_code),
    )
