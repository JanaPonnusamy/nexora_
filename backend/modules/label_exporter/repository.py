import os

from config.database import get_connection

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDL_FILES = (
    os.path.join(_SQL_DIR, "0001_label_review.sql"),
    os.path.join(_SQL_DIR, "0002_label_review_remarks.sql"),
    os.path.join(_SQL_DIR, "0003_label_assignment.sql"),
)
_schema_ready = False


def ensure_schema():
    """Create/extend dbo.label_review + dbo.label_location_history if absent.

    Every DDL file is idempotent (guarded by OBJECT_ID / COL_LENGTH), so this
    self-provisions on first use and is safe to re-run each startup - mirrors
    the procurement optimization_repository.ensure_schema pattern (split on
    GO). 0001/0002 were historically applied by hand; re-applying them is a
    no-op."""
    global _schema_ready
    if _schema_ready:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        for ddl_file in _DDL_FILES:
            with open(ddl_file, "r", encoding="utf-8") as fh:
                script = fh.read()
            for batch in (b.strip() for b in script.split("\nGO")):
                if batch:
                    cur.execute(batch)
        conn.commit()
    finally:
        conn.close()
    _schema_ready = True


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
    review_status="",
):
    """Main label-exporter grid: every active product matching the filters,
    with any Y/N + remarks review decision joined in. unit_description_mode
    is 'contains' (substring match), 'exact' (unit_description may be a
    comma-separated list for a multi-select filter), or 'null'
    (UnitDescription is blank/NULL) - 'null' ignores the unit_description
    text value. sublocation_filter is an optional comma-separated list of
    exact existing SubLocation values (multi-select 'old location' filter)."""
    # Unit filtering uses the EFFECTIVE (current) unit — a reviewer's correction
    # (dbo.label_review.unit_description) wins over the master p.UnitDescription
    # (spec §18: filter CALPOL by its corrected TAB, not its old SYP).
    eff_unit = "ISNULL(NULLIF(LTRIM(RTRIM(r.unit_description)), ''), ISNULL(p.UnitDescription, ''))"

    exact_values = [v.strip() for v in (unit_description or "").split(",") if v.strip()]
    if unit_description_mode == "exact" and exact_values:
        exact_clause = "LTRIM(RTRIM(%s)) IN (%s)" % (eff_unit, ", ".join("?" for _ in exact_values))
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
                MAX(b.GrnDate) AS last_purchase_date,
                MAX(b.LastSaleDate) AS last_sale_date,
                SUM(CASE WHEN ISNULL(b.Stock, 0) > 0 THEN ISNULL(b.Stock, 0) ELSE 0 END) AS live_batch_stock
            FROM sync.Batches b
            WHERE b.tenant_id = ?
              AND b.store_id = ?
            GROUP BY b.ProductCode
        )
        SELECT
            CAST(p.ProductCode AS NVARCHAR(50)) AS product_code,
            p.ProductName AS product_name,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.UnitDescription)), ''), '') AS NVARCHAR(100)) AS unit_description,
            CAST(ISNULL(p.SaleUnit, 0) AS DECIMAL(18, 2)) AS sale_unit,
            CAST(ISNULL(p.MRP, 0) AS DECIMAL(18, 2)) AS mrp,
            CAST(ISNULL(p.TotalStock, 0) AS DECIMAL(18, 2)) AS total_stock,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(p.SubLocation)), ''), '') AS NVARCHAR(50)) AS current_sublocation,
            CAST(ISNULL(agg.purchase_days, 0) AS INT) AS purchase_days,
            CAST(ISNULL(agg.sale_days, 0) AS INT) AS sale_days,
            CONVERT(VARCHAR(10), agg.last_purchase_date, 23) AS last_purchase_date,
            CONVERT(VARCHAR(10), agg.last_sale_date, 23) AS last_sale_date,
            CAST(ISNULL(agg.live_batch_stock, 0) AS DECIMAL(18, 2)) AS batch_stock,
            r.include_label,
            r.remarks,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(r.unit_description)), ''), '') AS NVARCHAR(100)) AS corrected_unit,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(r.old_unit_description)), ''), '') AS NVARCHAR(100)) AS old_unit_description,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(r.assigned_sublocation)), ''), '') AS NVARCHAR(50)) AS assigned_sublocation,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(r.old_sublocation)), ''), '') AS NVARCHAR(50)) AS old_sublocation,
            r.assignment_type,
            CAST(ISNULL(r.label_required, 0) AS BIT) AS label_required
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
                AND LTRIM(RTRIM({eff_unit})) = ''
                OR ? = 'exact'
                AND {exact_clause}
                OR ? = 'contains'
                AND (? = '' OR {eff_unit} LIKE '%' + ? + '%')
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
          AND (
                ? = ''
                OR (? = 'unreviewed' AND r.include_label IS NULL)
                OR (? IN ('Y', 'N') AND r.include_label = ?)
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
            review_status,
            review_status,
            review_status,
            review_status,
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
    """Last 12 months of movement for the right-side Monthly Trend chart, from
    sync.ProductTrans (populated monthly by the store agent). The chart groups
    the raw columns into four business movements; the mapping to real
    sync.ProductTrans columns is:

        Purchase + Tin  = PurchaseQuantity   + TransferInQuantity
        Sales + Tout    = SaleQuantity       + TransferOutQuantity
        Stock           = StockInHand
        Adjustment      = AdjustmentQuantity

    We return the raw components (never invent values); the frontend does the
    grouping so the legend labels stay a UI concern, and slices to the
    user-selected 4-12 month window client-side (no refetch on month change)."""
    return _fetch_all(
        """
        SELECT TOP 12
            CONVERT(VARCHAR(7), MonthOfStatistics, 120) AS month,
            CAST(ISNULL(SaleQuantity, 0) AS DECIMAL(18, 2)) AS sale_qty,
            CAST(ISNULL(PurchaseQuantity, 0) AS DECIMAL(18, 2)) AS purchase_qty,
            CAST(ISNULL(TransferInQuantity, 0) AS DECIMAL(18, 2)) AS transfer_in_qty,
            CAST(ISNULL(TransferOutQuantity, 0) AS DECIMAL(18, 2)) AS transfer_out_qty,
            CAST(ISNULL(AdjustmentQuantity, 0) AS DECIMAL(18, 2)) AS adjustment_qty,
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


# --------------------------------------------------------------------------
# Location assignment (Modes 1/2, SYP, single box)
# --------------------------------------------------------------------------

def get_products_for_assignment(tenant_id, store_id, product_codes):
    """Load the products the user picked, resolving the CORRECTED unit (a
    review unit_description override wins over the master UnitDescription -
    spec §Q) and each product's current effective location (its already-
    assigned box if any, else the shelf SubLocation)."""
    if not product_codes:
        return []
    placeholders = ", ".join("?" for _ in product_codes)
    return _fetch_all(
        f"""
        SELECT
            CAST(p.ProductCode AS NVARCHAR(50)) AS product_code,
            p.ProductName AS product_name,
            CAST(ISNULL(
                NULLIF(LTRIM(RTRIM(r.unit_description)), ''),
                NULLIF(LTRIM(RTRIM(p.UnitDescription)), '')
            ) AS NVARCHAR(100)) AS unit_description,
            CAST(ISNULL(
                NULLIF(LTRIM(RTRIM(r.assigned_sublocation)), ''),
                NULLIF(LTRIM(RTRIM(p.SubLocation)), '')
            ) AS NVARCHAR(50)) AS current_location,
            CAST(ISNULL(p.TotalStock, 0) AS DECIMAL(18, 2)) AS stock
        FROM sync.Products p
        LEFT JOIN dbo.label_review r
            ON r.tenant_id = p.tenant_id
           AND r.store_id = p.store_id
           AND r.product_code = CAST(p.ProductCode AS NVARCHAR(50))
        WHERE p.tenant_id = ?
          AND p.store_id = ?
          AND ISNULL(p.isactive, 1) = 1
          AND CAST(p.ProductCode AS NVARCHAR(50)) IN ({placeholders})
        """,
        (tenant_id, store_id, *product_codes),
    )


def get_box_occupancy(tenant_id, store_id, letter, exclude_codes=()):
    """Current occupancy per box for a letter: {box_id: product_count}, using
    each product's effective location (assigned box wins over shelf
    SubLocation). Products being (re)assigned in this run are excluded so they
    aren't double-counted against the box they currently sit in."""
    params = [tenant_id, store_id]
    exclude_clause = ""
    if exclude_codes:
        ph = ", ".join("?" for _ in exclude_codes)
        exclude_clause = f"AND CAST(p.ProductCode AS NVARCHAR(50)) NOT IN ({ph})"
        params.extend(exclude_codes)
    params.append(letter)
    rows = _fetch_all(
        f"""
        SELECT t.eff AS box, COUNT(*) AS cnt
        FROM (
            SELECT COALESCE(
                NULLIF(LTRIM(RTRIM(r.assigned_sublocation)), ''),
                NULLIF(LTRIM(RTRIM(p.SubLocation)), '')
            ) AS eff
            FROM sync.Products p
            LEFT JOIN dbo.label_review r
                ON r.tenant_id = p.tenant_id
               AND r.store_id = p.store_id
               AND r.product_code = CAST(p.ProductCode AS NVARCHAR(50))
            WHERE p.tenant_id = ?
              AND p.store_id = ?
              AND ISNULL(p.isactive, 1) = 1
              {exclude_clause}
        ) t
        WHERE t.eff IS NOT NULL AND t.eff LIKE ? + '%'
        GROUP BY t.eff
        """,
        tuple(params),
    )
    return {row["box"]: int(row["cnt"] or 0) for row in rows if row.get("box")}


def assign_locations(tenant_id, store_id, assignments, mode, assignment_type, user_id):
    """Commit a finalized assignment plan in ONE transaction (spec §V): upsert
    each product's dbo.label_review with its new box + captured old location,
    and append a dbo.label_location_history row for every real move. Either the
    whole batch commits or it rolls back."""
    if not assignments:
        return {"assigned": 0}
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for a in assignments:
            code = a["product_code"]
            old_loc = (a.get("old_location") or "").strip() or None
            new_box = a["box"]
            unit = (a.get("unit_description") or "").strip() or None
            cursor.execute(
                "SELECT id FROM dbo.label_review WHERE tenant_id = ? AND store_id = ? AND product_code = ?",
                (tenant_id, store_id, code),
            )
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(
                    """
                    INSERT INTO dbo.label_review (
                        tenant_id, store_id, product_code, product_name,
                        unit_description, old_sublocation, assigned_sublocation,
                        assignment_mode, assignment_type, assigned_by, assigned_at,
                        label_required, stock, sale_days, purchase_days
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), 1, ?, ?, ?)
                    """,
                    (
                        tenant_id, store_id, code, a.get("product_name"),
                        unit, old_loc, new_box, mode, assignment_type, user_id,
                        a.get("stock"), a.get("sale_days"), a.get("purchase_days"),
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE dbo.label_review
                    SET product_name = COALESCE(product_name, ?),
                        unit_description = COALESCE(?, unit_description),
                        old_sublocation = COALESCE(NULLIF(LTRIM(RTRIM(old_sublocation)), ''), ?),
                        assigned_sublocation = ?,
                        assignment_mode = ?,
                        assignment_type = ?,
                        assigned_by = ?,
                        assigned_at = SYSUTCDATETIME(),
                        label_required = 1,
                        stock = COALESCE(?, stock),
                        sale_days = COALESCE(?, sale_days),
                        purchase_days = COALESCE(?, purchase_days),
                        updated_at = SYSUTCDATETIME()
                    WHERE tenant_id = ? AND store_id = ? AND product_code = ?
                    """,
                    (
                        a.get("product_name"), unit, old_loc, new_box, mode,
                        assignment_type, user_id, a.get("stock"), a.get("sale_days"),
                        a.get("purchase_days"), tenant_id, store_id, code,
                    ),
                )
            if old_loc != new_box:
                cursor.execute(
                    """
                    INSERT INTO dbo.label_location_history (
                        tenant_id, store_id, product_code, old_location, new_location,
                        unit_description, assignment_mode, assignment_type, assigned_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tenant_id, store_id, code, old_loc, new_box, unit, mode, assignment_type, user_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
    return {"assigned": len(assignments)}


def correct_unit(tenant_id, store_id, product_code, new_unit, current_unit, user_id):
    """Reviewer corrects a product's unit (e.g. CALPOL SYP -> TAB). Captures the
    original master unit into old_unit_description ONCE (never destroyed), and
    stores the correction in unit_description. Auto-saved (spec §D)."""
    existing = _fetch_one(
        "SELECT id FROM dbo.label_review WHERE tenant_id = ? AND store_id = ? AND product_code = ?",
        (tenant_id, store_id, product_code),
    )
    if existing is None:
        _execute(
            """
            INSERT INTO dbo.label_review (
                tenant_id, store_id, product_code, old_unit_description,
                unit_description, reviewed_by, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
            """,
            (tenant_id, store_id, product_code, current_unit or None, new_unit or None, user_id),
        )
        return
    _execute(
        """
        UPDATE dbo.label_review
        SET old_unit_description = COALESCE(NULLIF(LTRIM(RTRIM(old_unit_description)), ''), ?),
            unit_description = ?,
            reviewed_by = ?,
            updated_at = SYSUTCDATETIME()
        WHERE tenant_id = ? AND store_id = ? AND product_code = ?
        """,
        (current_unit or None, new_unit or None, user_id, tenant_id, store_id, product_code),
    )


def correct_location(tenant_id, store_id, product_code, new_location, current_location, user_id):
    """Manual single-product box/letter override (spec-parity with
    correct_unit): lets a reviewer type/pick a location directly on the grid,
    bypassing the standard-box/SYP-bucket assignment engine (assign_locations)
    entirely. Captures whatever was previously assigned into old_sublocation
    ONCE (never overwritten by a later correction, same COALESCE pattern as
    correct_unit), sets assigned_sublocation to the new value, and marks
    label_required = 1 so it enters the print queue like an algorithmic
    assignment would. Logs to dbo.label_location_history for the same audit
    trail assign_locations writes, when the location actually changed."""
    new_location = (new_location or "").strip() or None
    current_location = (current_location or "").strip() or None
    existing = _fetch_one(
        "SELECT id FROM dbo.label_review WHERE tenant_id = ? AND store_id = ? AND product_code = ?",
        (tenant_id, store_id, product_code),
    )
    if existing is None:
        _execute(
            """
            INSERT INTO dbo.label_review (
                tenant_id, store_id, product_code, old_sublocation,
                assigned_sublocation, assignment_mode, assignment_type,
                assigned_by, assigned_at, label_required, reviewed_by, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, 'manual', 'manual', ?, SYSUTCDATETIME(), 1, ?, SYSUTCDATETIME())
            """,
            (tenant_id, store_id, product_code, current_location, new_location, user_id, user_id),
        )
    else:
        _execute(
            """
            UPDATE dbo.label_review
            SET old_sublocation = COALESCE(NULLIF(LTRIM(RTRIM(old_sublocation)), ''), ?),
                assigned_sublocation = ?,
                assignment_mode = 'manual',
                assignment_type = 'manual',
                assigned_by = ?,
                assigned_at = SYSUTCDATETIME(),
                label_required = 1,
                updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ? AND store_id = ? AND product_code = ?
            """,
            (current_location, new_location, user_id, tenant_id, store_id, product_code),
        )
    if current_location != new_location:
        _execute(
            """
            INSERT INTO dbo.label_location_history (
                tenant_id, store_id, product_code, old_location, new_location,
                assignment_mode, assignment_type, assigned_by
            )
            VALUES (?, ?, ?, ?, ?, 'manual', 'manual', ?)
            """,
            (tenant_id, store_id, product_code, current_location, new_location, user_id),
        )


def get_label_queue(tenant_id, store_id):
    """Products with an assigned box and label_required = 1 (spec §W). Print/
    export reads from here; assignment and printing stay separate."""
    return _fetch_all(
        """
        SELECT
            CAST(r.product_code AS NVARCHAR(50)) AS product_code,
            CAST(ISNULL(r.product_name, p.ProductName) AS NVARCHAR(200)) AS product_name,
            CAST(r.assigned_sublocation AS NVARCHAR(50)) AS location,
            CAST(ISNULL(NULLIF(LTRIM(RTRIM(r.unit_description)), ''), p.UnitDescription) AS NVARCHAR(100)) AS unit_description,
            CAST(ISNULL(p.MRP, 0) AS DECIMAL(18, 2)) AS mrp,
            CAST(ISNULL(p.SaleUnit, 0) AS DECIMAL(18, 2)) AS sale_unit,
            r.assignment_type,
            CONVERT(VARCHAR(19), r.assigned_at, 120) AS assigned_at,
            CONVERT(VARCHAR(19), r.label_created_at, 120) AS label_created_at
        FROM dbo.label_review r
        LEFT JOIN sync.Products p
            ON p.tenant_id = r.tenant_id
           AND p.store_id = r.store_id
           AND CAST(p.ProductCode AS NVARCHAR(50)) = r.product_code
        WHERE r.tenant_id = ?
          AND r.store_id = ?
          AND ISNULL(r.label_required, 0) = 1
          AND NULLIF(LTRIM(RTRIM(r.assigned_sublocation)), '') IS NOT NULL
        ORDER BY r.assigned_sublocation, ISNULL(r.product_name, p.ProductName)
        """,
        (tenant_id, store_id),
    )


def mark_labels_printed(tenant_id, store_id, product_codes):
    """Stamp label_created_at when labels are printed/exported (spec §W)."""
    if not product_codes:
        return
    conn = get_connection()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join("?" for _ in product_codes)
        cursor.execute(
            f"""
            UPDATE dbo.label_review
            SET label_created_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ? AND store_id = ? AND product_code IN ({placeholders})
            """,
            (tenant_id, store_id, *product_codes),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def clear_assignment_state(tenant_id, store_id, product_codes):
    """Reset ONLY the Label-Exporter assignment result for the given products
    (spec §10): null the assigned box + assignment/label bookkeeping so their
    status falls back to PENDING (if still reviewed Y) or NOT_STARTED. Never
    touches include_label (the Y/N review), old_sublocation, the unit
    correction, or sync.Products — master/source data is left intact. Records a
    history row for each box actually cleared."""
    if not product_codes:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join("?" for _ in product_codes)
        # Audit the boxes we are about to vacate before nulling them.
        cursor.execute(
            f"""
            INSERT INTO dbo.label_location_history
                (tenant_id, store_id, product_code, old_location, new_location, assignment_mode, assignment_type)
            SELECT tenant_id, store_id, product_code, assigned_sublocation, NULL, 'clear', 'clear'
            FROM dbo.label_review
            WHERE tenant_id = ? AND store_id = ?
              AND product_code IN ({placeholders})
              AND NULLIF(LTRIM(RTRIM(assigned_sublocation)), '') IS NOT NULL
            """,
            (tenant_id, store_id, *product_codes),
        )
        cursor.execute(
            f"""
            UPDATE dbo.label_review
            SET assigned_sublocation = NULL,
                assignment_mode = NULL,
                assignment_type = NULL,
                assigned_by = NULL,
                assigned_at = NULL,
                label_required = 0,
                label_created_at = NULL,
                updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ? AND store_id = ? AND product_code IN ({placeholders})
            """,
            (tenant_id, store_id, *product_codes),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    finally:
        cursor.close()
        conn.close()


def clear_review_state(tenant_id, store_id, product_codes):
    """Reset the review workflow for the given products (spec §11): clear the
    Y/N decision AND the assignment/label state so they return to NOT_REVIEWED.
    Preserves the unit correction (old_unit_description/unit_description),
    old_sublocation and remarks, and never touches sync.Products. Callers must
    confirm first — this is the explicit 'Reset Review' action."""
    if not product_codes:
        return 0
    # Vacate any assigned boxes first (audited), then clear the review flag.
    clear_assignment_state(tenant_id, store_id, product_codes)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join("?" for _ in product_codes)
        cursor.execute(
            f"""
            UPDATE dbo.label_review
            SET include_label = NULL,
                reviewed_at = NULL,
                updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ? AND store_id = ? AND product_code IN ({placeholders})
            """,
            (tenant_id, store_id, *product_codes),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    finally:
        cursor.close()
        conn.close()


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
