"""Read-only data access for the Stock Check Report module.

Ported from the legacy VB6 OrderRpt "Stock Check" report (D:/OrderRpt/
ReportsExport.frm, Command9_Click / Command11_Click): a physical-count sheet
of every batch in a sublocation range. The legacy app queried the store's
live BATCHES/PRODUCTS tables directly; this reads the already-synced
`sync.Batches` / `sync.Products` tables in NEXORA_PLATFORM instead, so the
caller triggers a sync first (see sync.runtime_service) and reports off that.

Supplier is resolved from sync.Products.SupplierCode (a persistent product
field), not from PurchaseTrans -- the TI-transfer SupplierCode collision
documented in modules/nonmoving_analysis/repository.py only affects
PurchaseTrans-derived "last supplier" lookups, not this field.
"""

from config.database import get_connection


def search_sublocations(tenant_id, store_id, search_text):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT TOP 20 LTRIM(RTRIM(SubLocation)) AS sublocation
            FROM sync.Products
            WHERE tenant_id = ?
              AND store_id  = ?
              AND SubLocation IS NOT NULL
              AND LTRIM(RTRIM(SubLocation)) <> ''
              AND LTRIM(RTRIM(SubLocation)) LIKE ? + '%'
            ORDER BY sublocation
            """,
            (tenant_id, store_id, search_text),
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def list_suppliers(tenant_id, store_id):
    """Suppliers that currently own at least one product with a sublocation
    assigned (the universe this report can ever show), so the dropdown never
    offers a supplier with nothing to filter to."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT p.SupplierCode             AS supplier_code,
                   MAX(RTRIM(s.suppliername))          AS supplier_name
            FROM sync.Products p
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = p.tenant_id
               AND s.store_id  = p.store_id
               AND s.suppliercode = p.SupplierCode
            WHERE p.tenant_id = ? AND p.store_id = ?
              AND p.SupplierCode IS NOT NULL
              AND p.SubLocation IS NOT NULL
              AND LTRIM(RTRIM(p.SubLocation)) <> ''
            GROUP BY p.SupplierCode
            ORDER BY supplier_name
            """,
            (tenant_id, store_id),
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def list_units(tenant_id, store_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT RTRIM(UnitDescription) AS unit_description
            FROM sync.Products
            WHERE tenant_id = ? AND store_id = ?
              AND UnitDescription IS NOT NULL
              AND RTRIM(UnitDescription) <> ''
              AND SubLocation IS NOT NULL
              AND LTRIM(RTRIM(SubLocation)) <> ''
            ORDER BY unit_description
            """,
            (tenant_id, store_id),
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def get_stock_check_rows(tenant_id, store_id, filters):
    """filters is a dict with the keys below (all optional / already
    trimmed/validated by the service layer):
      sublocation_from, sublocation_to    -- string range on p.SubLocation
      product_code_from, product_code_to  -- numeric range (int) on b.ProductCode
      product_name                        -- substring match
      supplier_code                       -- exact match on p.SupplierCode
      unit_description                    -- exact match on p.UnitDescription
      batch_code                          -- substring match on b.BatchCode
      expiry_from, expiry_to              -- date range on b.ExpiryDate
      min_stock, max_stock                -- range on b.Stock
      include_zero_stock                  -- bool; default excludes zero/neg
      include_negative_stock              -- bool
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        where = [
            "b.tenant_id = ?",
            "b.store_id  = ?",
            "p.SubLocation IS NOT NULL",
            "LTRIM(RTRIM(p.SubLocation)) <> ''",
        ]
        params = [tenant_id, store_id]

        sub_from = filters.get("sublocation_from")
        sub_to = filters.get("sublocation_to")
        if sub_from and sub_to:
            where.append("LTRIM(RTRIM(p.SubLocation)) BETWEEN ? AND ?")
            params += [sub_from, sub_to]

        code_from = filters.get("product_code_from")
        code_to = filters.get("product_code_to")
        if code_from is not None and code_to is not None:
            # ProductCode is int (not alphanumeric) in sync.Products/Batches,
            # so this is a numeric range, not a string BETWEEN.
            where.append("b.ProductCode BETWEEN ? AND ?")
            params += [code_from, code_to]

        product_name = filters.get("product_name")
        if product_name:
            where.append("p.ProductName LIKE ?")
            params.append(f"%{product_name}%")

        supplier_code = filters.get("supplier_code")
        if supplier_code:
            where.append("p.SupplierCode = ?")
            params.append(supplier_code)

        unit_description = filters.get("unit_description")
        if unit_description:
            where.append("RTRIM(p.UnitDescription) = ?")
            params.append(unit_description)

        batch_code = filters.get("batch_code")
        if batch_code:
            where.append("b.BatchCode LIKE ?")
            params.append(f"%{batch_code}%")

        expiry_from = filters.get("expiry_from")
        expiry_to = filters.get("expiry_to")
        if expiry_from and expiry_to:
            where.append("CAST(b.ExpiryDate AS DATE) BETWEEN ? AND ?")
            params += [expiry_from, expiry_to]

        min_stock = filters.get("min_stock")
        if min_stock is not None:
            where.append("ISNULL(b.Stock, 0) >= ?")
            params.append(min_stock)

        max_stock = filters.get("max_stock")
        if max_stock is not None:
            where.append("ISNULL(b.Stock, 0) <= ?")
            params.append(max_stock)

        if filters.get("include_negative_stock"):
            pass  # no lower-bound clamp
        elif filters.get("include_zero_stock"):
            where.append("ISNULL(b.Stock, 0) >= 0")
        else:
            where.append("ISNULL(b.Stock, 0) > 0")

        cursor.execute(
            f"""
            ;WITH ProductAgg AS (
                -- Last purchase/sale per PRODUCT across ALL its batches (not just
                -- the ones still holding stock) -- a product that sold out an
                -- older batch recently but hasn't touched its newer batches yet
                -- must not be seen as non-moving just because the in-stock
                -- batches themselves were never sold from.
                SELECT ProductCode,
                       DATEDIFF(DAY, MAX(GrnDate), GETDATE())      AS purchase_days,
                       DATEDIFF(DAY, MAX(LastSaleDate), GETDATE()) AS sale_days
                FROM sync.Batches
                WHERE tenant_id = ? AND store_id = ?
                GROUP BY ProductCode
            )
            -- total_stock stays sourced from sync.Products.TotalStock (NOT
            -- SUM(Batches.Stock)): cross-checked against sync.ProductTrans
            -- .StockInHand -- the authoritative store-stock source documented in
            -- modules/procurement/_dbutil.py:store_stock_expr() -- TotalStock
            -- matches StockInHand exactly. SUM(Batches.Stock) is the value that
            -- disagrees with both, so the mismatch is stale/inflated batch-level
            -- quantities in sync.Batches, not a bad total_stock source here.
            SELECT
                CAST(b.ProductCode AS NVARCHAR(50)) AS product_code,
                LTRIM(RTRIM(p.SubLocation))          AS sublocation,
                p.ProductName                        AS product_name,
                CAST(p.SupplierCode AS VARCHAR(100)) AS supplier_code,
                RTRIM(sup.suppliername)              AS supplier_name,
                RTRIM(p.UnitDescription)             AS unit_description,
                ISNULL(p.TotalStock, 0)              AS total_stock,
                ISNULL(b.Stock, 0)                   AS batch_stock,
                CAST(b.ExpiryDate AS DATE)           AS expiry_date,
                ISNULL(b.MRP, 0)                     AS mrp,
                CAST(b.SaleUnit AS NVARCHAR(50))     AS sale_unit,
                CAST(b.BatchCode AS VARCHAR(50))     AS batch_code,
                agg.purchase_days                    AS purchase_days,
                agg.sale_days                        AS sale_days
            FROM sync.Batches b
            INNER JOIN sync.Products p
                ON p.tenant_id = b.tenant_id
               AND p.store_id  = b.store_id
               AND p.ProductCode = b.ProductCode
            INNER JOIN ProductAgg agg
                ON agg.ProductCode = b.ProductCode
            LEFT JOIN sync.Suppliers sup
                ON sup.tenant_id = p.tenant_id
               AND sup.store_id  = p.store_id
               AND sup.suppliercode = p.SupplierCode
            WHERE {' AND '.join(where)}
            ORDER BY p.SubLocation, p.ProductName, b.ExpiryDate
            """,
            (tenant_id, store_id, *params),
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            if row.get("expiry_date") is not None:
                row["expiry_date"] = row["expiry_date"].isoformat()
        return rows
    finally:
        cursor.close()
        conn.close()
