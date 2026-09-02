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


def _execute(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def list_products_for_review(tenant_id, store_id, starts_with):
    """All active products for a letter, with any existing review decision
    joined in. Unlike search_products, this is not filtered by a stock rule -
    the point is to walk every product on the shelf for that letter."""
    return _fetch_all(
        """
        SELECT TOP 500
            CAST(p.ProductCode AS NVARCHAR(50)) AS product_code,
            p.ProductName AS product_name,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.UnitDescription)), ''), '') AS NVARCHAR(100)) AS unit_description,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.SubLocation)), ''), '') AS NVARCHAR(50)) AS current_sublocation,
            CAST(ISNULL(p.MRP, 0) AS DECIMAL(18, 2)) AS mrp,
            CAST(ISNULL(p.TotalStock, 0) AS DECIMAL(18, 2)) AS total_stock,
            r.include_label,
            r.product_kind,
            r.suggested_unit_description,
            ISNULL(r.suggestion_status, 'none') AS suggestion_status,
            r.final_unit_description
        FROM sync.Products p
        LEFT JOIN dbo.label_review r
            ON r.tenant_id = p.tenant_id
           AND r.store_id = p.store_id
           AND r.product_code = CAST(p.ProductCode AS NVARCHAR(50))
        WHERE p.tenant_id = ?
          AND p.store_id = ?
          AND ISNULL(p.isactive, 1) = 1
          AND (? = '' OR p.ProductName LIKE ? + '%')
        ORDER BY p.ProductName
        """,
        (tenant_id, store_id, starts_with, starts_with),
    )


def upsert_review(
    tenant_id,
    store_id,
    product_code,
    include_label,
    product_kind,
    suggested_unit_description,
    user_id,
):
    """Store-user action: set include Y/N, counter/consumer, and/or submit a
    unit-description suggestion. A submitted suggestion always (re)opens the
    row to 'pending' so a super admin has to look at it again."""
    is_suggestion = suggested_unit_description is not None and suggested_unit_description != ''
    is_review = include_label is not None or product_kind is not None

    existing = _fetch_one(
        "SELECT id FROM dbo.label_review WHERE tenant_id = ? AND store_id = ? AND product_code = ?",
        (tenant_id, store_id, product_code),
    )

    if existing is None:
        _execute(
            """
            INSERT INTO dbo.label_review (
                tenant_id, store_id, product_code, include_label, product_kind,
                suggested_unit_description, suggestion_status,
                suggested_by, suggested_at, reviewed_by, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 1 THEN SYSUTCDATETIME() END, ?, CASE WHEN ? = 1 THEN SYSUTCDATETIME() END)
            """,
            (
                tenant_id, store_id, product_code, include_label, product_kind,
                suggested_unit_description if is_suggestion else None,
                'pending' if is_suggestion else 'none',
                user_id if is_suggestion else None, 1 if is_suggestion else 0,
                user_id if is_review else None, 1 if is_review else 0,
            ),
        )
        return

    set_clauses = ["updated_at = SYSUTCDATETIME()"]
    params: list = []
    if include_label is not None:
        set_clauses.append("include_label = ?")
        params.append(include_label)
    if product_kind is not None:
        set_clauses.append("product_kind = ?")
        params.append(product_kind)
    if is_review:
        set_clauses.append("reviewed_by = ?")
        set_clauses.append("reviewed_at = SYSUTCDATETIME()")
        params.append(user_id)
    if is_suggestion:
        set_clauses.append("suggested_unit_description = ?")
        set_clauses.append("suggestion_status = 'pending'")
        set_clauses.append("suggested_by = ?")
        set_clauses.append("suggested_at = SYSUTCDATETIME()")
        params.extend([suggested_unit_description, user_id])

    params.extend([tenant_id, store_id, product_code])
    _execute(
        f"""
        UPDATE dbo.label_review
        SET {', '.join(set_clauses)}
        WHERE tenant_id = ? AND store_id = ? AND product_code = ?
        """,
        params,
    )


def list_pending_suggestions(tenant_id, store_id):
    return _fetch_all(
        """
        SELECT
            r.tenant_id, r.store_id,
            r.product_code,
            p.ProductName AS product_name,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.UnitDescription)), ''), '') AS NVARCHAR(100)) AS current_unit_description,
            r.suggested_unit_description,
            r.suggested_by,
            r.suggested_at,
            r.suggestion_status
        FROM dbo.label_review r
        JOIN sync.Products p
            ON p.tenant_id = r.tenant_id
           AND p.store_id = r.store_id
           AND CAST(p.ProductCode AS NVARCHAR(50)) = r.product_code
        WHERE r.suggestion_status = 'pending'
          AND (? = '' OR r.tenant_id = ?)
          AND (? = '' OR r.store_id = ?)
        ORDER BY r.suggested_at
        """,
        (tenant_id or '', tenant_id, store_id or '', store_id),
    )


def decide_suggestion(tenant_id, store_id, product_code, approved, final_unit_description, user_id):
    _execute(
        """
        UPDATE dbo.label_review
        SET suggestion_status = ?,
            final_unit_description = ?,
            decided_by = CAST(? AS UNIQUEIDENTIFIER),
            decided_at = SYSUTCDATETIME(),
            updated_at = SYSUTCDATETIME()
        WHERE tenant_id = ? AND store_id = ? AND product_code = ?
        """,
        (
            'approved' if approved else 'rejected',
            final_unit_description if approved else None,
            user_id,
            tenant_id, store_id, product_code,
        ),
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
