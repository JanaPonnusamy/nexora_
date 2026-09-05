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
    unit_description_mode,
    box_number,
    stock_filter,
    only_null_sublocation,
    only_sale_unit_gt_one,
    sublocation_filter="",
):
    """Main label-exporter grid: every active product matching the filters,
    with any Y/N + remarks review decision joined in. unit_description_mode
    is 'contains' (substring match), 'exact' (unit_description may be a
    comma-separated list for a multi-select filter), or 'null'
    (UnitDescription is blank/NULL) - 'null' ignores the unit_description
    text value. sublocation_filter is an optional comma-separated list of
    exact existing SubLocation values (multi-select 'old location' filter)."""
    exact_values = [v.strip() for v in (unit_description or "").split(",") if v.strip()]
    if unit_description_mode == "exact" and exact_values:
        exact_clause = "LTRIM(RTRIM(ISNULL(p.UnitDescription, ''))) IN (%s)" % ", ".join("?" for _ in exact_values)
        exact_params = list(exact_values)
    else:
        exact_clause = "1 = 1"
        exact_params = []

    subloc_values = [v.strip() for v in (sublocation_filter or "").split(",") if v.strip()]
    if subloc_values:
        subloc_clause = "LTRIM(RTRIM(ISNULL(p.SubLocation, ''))) IN (%s)" % ", ".join("?" for _ in subloc_values)
        subloc_params = list(subloc_values)
    else:
        subloc_clause = "1 = 1"
        subloc_params = []

    rows = _fetch_all(
        f"""
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
            CAST(ISNULL(agg.live_batch_stock, 0) AS DECIMAL(18, 2)) AS batch_stock,
            r.include_label,
            r.remarks
        FROM sync.Products p
        LEFT JOIN ProductAgg agg
            ON agg.ProductCode = p.ProductCode
        LEFT JOIN dbo.label_review r
            ON r.tenant_id = p.tenant_id
           AND r.store_id = p.store_id
           AND r.product_code = CAST(p.ProductCode AS NVARCHAR(50))
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
                ? = 'null'
                AND LTRIM(RTRIM(ISNULL(p.UnitDescription, ''))) = ''
                OR ? = 'exact'
                AND {exact_clause}
                OR ? = 'contains'
                AND (? = '' OR ISNULL(p.UnitDescription, '') LIKE '%' + ? + '%')
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
          AND ({subloc_clause})
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
                OR (
                    ? = 'zero_stale'
                    AND ISNULL(p.TotalStock, 0) = 0
                    AND (agg.sale_days IS NULL OR agg.sale_days > 90)
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
            unit_description_mode,
            unit_description_mode, *exact_params,
            unit_description_mode, unit_description, unit_description,
            box_number,
            box_number,
            1 if only_null_sublocation else 0,
            box_number,
            *subloc_params,
            1 if only_sale_unit_gt_one else 0,
            stock_filter,
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


def get_sublocations(tenant_id, store_id):
    """Distinct existing SubLocation values, for the 'Old Loc' multi-select
    filter - so users pick from what's really in the table instead of
    free-typing a location that may not exist."""
    rows = _fetch_all(
        """
        SELECT DISTINCT TOP 300
            CAST(LTRIM(RTRIM(SubLocation)) AS NVARCHAR(50)) AS sublocation
        FROM sync.Products
        WHERE tenant_id = ?
          AND store_id = ?
          AND ISNULL(isactive, 1) = 1
          AND LTRIM(RTRIM(ISNULL(SubLocation, ''))) <> ''
        ORDER BY CAST(LTRIM(RTRIM(SubLocation)) AS NVARCHAR(50))
        """,
        (tenant_id, store_id),
    )
    return [row["sublocation"] for row in rows if row.get("sublocation")]


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


def upsert_review(tenant_id, store_id, product_code, include_label, remarks, user_id):
    """Reviewer action (any store-scoped user): set include Y/N and/or a
    remarks note (predefined tag like 'Counter'/'SYP', or a free-text unit
    description correction)."""
    existing = _fetch_one(
        "SELECT id FROM dbo.label_review WHERE tenant_id = ? AND store_id = ? AND product_code = ?",
        (tenant_id, store_id, product_code),
    )

    if existing is None:
        _execute(
            """
            INSERT INTO dbo.label_review (
                tenant_id, store_id, product_code, include_label, remarks,
                reviewed_by, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
            """,
            (tenant_id, store_id, product_code, include_label, remarks, user_id),
        )
        return

    _execute(
        """
        UPDATE dbo.label_review
        SET include_label = COALESCE(?, include_label),
            remarks = COALESCE(?, remarks),
            reviewed_by = ?,
            reviewed_at = SYSUTCDATETIME(),
            updated_at = SYSUTCDATETIME()
        WHERE tenant_id = ? AND store_id = ? AND product_code = ?
        """,
        (include_label, remarks, user_id, tenant_id, store_id, product_code),
    )


def bulk_set_include_label(tenant_id, store_id, product_codes, include_label, user_id):
    """Bulk review action (e.g. 'mark all visible Y'): one connection, one
    UPDATE for codes that already have a row, one INSERT for the rest -
    avoids opening a connection per product like a loop over upsert_review
    would for a few hundred rows."""
    if not product_codes:
        return
    conn = get_connection()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join("?" for _ in product_codes)
        cursor.execute(
            f"""
            UPDATE dbo.label_review
            SET include_label = ?, reviewed_by = ?, reviewed_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ? AND store_id = ? AND product_code IN ({placeholders})
            """,
            (include_label, user_id, tenant_id, store_id, *product_codes),
        )
        cursor.execute(
            f"""
            SELECT product_code FROM dbo.label_review
            WHERE tenant_id = ? AND store_id = ? AND product_code IN ({placeholders})
            """,
            (tenant_id, store_id, *product_codes),
        )
        existing = {row[0] for row in cursor.fetchall()}
        missing = [code for code in product_codes if code not in existing]
        for code in missing:
            cursor.execute(
                """
                INSERT INTO dbo.label_review (tenant_id, store_id, product_code, include_label, reviewed_by, reviewed_at)
                VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME())
                """,
                (tenant_id, store_id, code, include_label, user_id),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def assign_sublocation(tenant_id, store_id, product_code, sublocation, user_id):
    """Super-admin action: set the shelf/box SubLocation directly on
    sync.Products (the platform mirror). Not pushed down to the store's own
    SQL Server yet - may be overwritten by that store's next sync, same
    caveat as the old unit-description-suggestion feature."""
    _execute(
        """
        UPDATE sync.Products
        SET SubLocation = NULLIF(LTRIM(RTRIM(?)), '')
        WHERE tenant_id = ?
          AND store_id = ?
          AND CAST(ProductCode AS NVARCHAR(50)) = ?
        """,
        (sublocation, tenant_id, store_id, product_code),
    )


def get_product_trend(tenant_id, store_id, product_code):
    """Last 12 months of sale/purchase quantity + stock snapshot for the
    right-side trend panel, from sync.ProductTrans (populated monthly by the
    store agent)."""
    return _fetch_all(
        """
        SELECT TOP 12
            CONVERT(VARCHAR(7), MonthOfStatistics, 120) AS month,
            CAST(ISNULL(SaleQuantity, 0) AS DECIMAL(18, 2)) AS sale_qty,
            CAST(ISNULL(PurchaseQuantity, 0) AS DECIMAL(18, 2)) AS purchase_qty,
            CAST(ISNULL(StockInHand, 0) AS DECIMAL(18, 2)) AS stock_in_hand
        FROM sync.ProductTrans
        WHERE tenant_id = ?
          AND store_id = ?
          AND ProductCode = ?
        ORDER BY MonthOfStatistics DESC
        """,
        (tenant_id, store_id, product_code),
    )


def get_product_purchases(tenant_id, store_id, product_code):
    """Last 30 purchase/GRN lines for the right-side intelligence panel."""
    return _fetch_all(
        """
        SELECT TOP 30
            CAST(ISNULL(t.stockreceived, 0) AS DECIMAL(18, 2)) AS stock,
            CAST(ISNULL(t.FreeQty, 0) AS DECIMAL(18, 2)) AS free_qty,
            CAST(ISNULL(t.ProductDiscPercent, 0) AS DECIMAL(9, 2)) AS discount_pct,
            CAST(ISNULL(t.itemcost, 0) AS DECIMAL(18, 2)) AS item_cost,
            CAST(ISNULL(t.purchaseprice, 0) AS DECIMAL(18, 2)) AS ptr,
            CAST(ISNULL(t.mrp, 0) AS DECIMAL(18, 2)) AS mrp,
            CONVERT(VARCHAR(10), t.grndate, 120) AS grn_date,
            s.suppliername AS supplier_name
        FROM sync.PurchaseTrans t
        LEFT JOIN sync.Suppliers s
            ON s.tenant_id = t.tenant_id
           AND s.store_id = t.store_id
           AND s.suppliercode = t.SupplierCode
        WHERE t.tenant_id = ?
          AND t.store_id = ?
          AND t.ProductCode = ?
        ORDER BY t.grndate DESC
        """,
        (tenant_id, store_id, product_code),
    )


def get_product_sales(tenant_id, store_id, product_code):
    """Last 30 bill/sale lines for the right-side intelligence panel."""
    return _fetch_all(
        """
        SELECT TOP 30
            CAST(ISNULL(ps.Quantity, 0) AS DECIMAL(18, 2)) AS qty,
            CONVERT(VARCHAR(16), ps.TransactionDate, 120) AS bill_time,
            CAST(si.DeliverySalesRep AS NVARCHAR(50)) AS salesman,
            si.CustomerName AS customer,
            CAST(ISNULL(ps.DiscountPercentage, 0) AS DECIMAL(9, 2)) AS discount_pct,
            CAST(ISNULL(ps.MRP, 0) AS DECIMAL(18, 2)) AS mrp
        FROM sync.ProductSaleInformation ps
        LEFT JOIN sync.SaleInformation si
            ON si.tenant_id = ps.tenant_id
           AND si.store_id = ps.store_id
           AND si.BillNumber = ps.BillNumber
        WHERE ps.tenant_id = ?
          AND ps.store_id = ?
          AND ps.ProductCode = ?
        ORDER BY ps.TransactionDate DESC
        """,
        (tenant_id, store_id, product_code),
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
