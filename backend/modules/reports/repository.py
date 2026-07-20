"""Data access for the Reports module — read-only, over the synced `sync.*`
tables in NEXORA_PLATFORM.

Every query is scoped by tenant_id + store_id (the legacy WinForms reports ran
against a single store's live DB; here the same store lives in `sync.*` keyed by
tenant_id/store_id). Adapted faithfully from the legacy `Reports.vb` SQL; the
only structural change is the tenant/store scoping and — where a legacy source
table is not synced — an equivalent derived from a synced table (noted inline).

All functions return ``(columns, rows)`` where ``columns`` is the ordered list of
column names as returned by SQL Server and ``rows`` is a list of dicts. This lets
the service render dynamic-column reports (Monthly, EYRUS) uniformly.
"""

from datetime import date, timedelta

from config.database import get_connection


def _run(sql, params):
    """Run a read query and return (ordered column names, list-of-dict rows)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Supplier lookup (for Non-Moving / Purchased-Not-Sold filters)
# ---------------------------------------------------------------------------

def search_suppliers(tenant_id, store_id, query, limit=30):
    q = (query or "").strip()
    sql = f"""
        SELECT TOP ({int(limit)})
            CAST(suppliercode AS VARCHAR(100)) AS supplier_code,
            CAST(suppliername AS VARCHAR(300)) AS supplier_name
        FROM sync.Suppliers
        WHERE tenant_id = ? AND store_id = ?
          AND ( ? = '' OR suppliername LIKE '%' + ? + '%' )
        ORDER BY suppliername
    """
    _, rows = _run(sql, (tenant_id, store_id, q, q))
    return rows


# ---------------------------------------------------------------------------
# 1. Stock Adjustment Report  (legacy GenerateReport)
# ---------------------------------------------------------------------------

def stock_adj(tenant_id, store_id, from_date, to_date):
    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY p.ProductName) AS SNo,
            p.ProductName,
            SUM(ps.Quantity)                 AS TotalQuantity,
            MIN(ps.Expirydate)               AS Expirydate,
            MAX(p.SaleUnit)                  AS SaleUnit,
            MAX(p.PurchasePrice)             AS PurchasePrice,
            MAX(ps.MRP)                      AS MRP,
            SUM(ps.Transactionamount)        AS Amount,
            CASE ps.SeriesName
                WHEN 'SA' THEN 'Stock Adj'
                WHEN 'ER' THEN 'Expiry Return'
                WHEN 'N'  THEN 'Normal'
                ELSE 'Unknown'
            END AS SeriesName
        FROM sync.ProductSaleInformation ps
        INNER JOIN sync.Products p
            ON p.tenant_id = ps.tenant_id AND p.store_id = ps.store_id
           AND p.ProductCode = ps.ProductCode
        WHERE ps.tenant_id = ? AND ps.store_id = ?
          AND CAST(ps.TransactionDate AS DATE) BETWEEN ? AND ?
          AND ps.SeriesName IN ('SA', 'ER', 'N')
        GROUP BY p.ProductName, ps.SeriesName
        HAVING SUM(ps.Quantity) <> 0
        ORDER BY p.ProductName
    """
    return _run(sql, (tenant_id, store_id, from_date, to_date))


# ---------------------------------------------------------------------------
# 2. Sales (Discount) Report  (legacy GeneratesalesReport)
# ---------------------------------------------------------------------------

def sales_discount(tenant_id, store_id, from_date, to_date):
    sql = """
        WITH DiscountSummary AS (
            SELECT DiscountPercentage,
                   SUM(Transactionamount) AS TotalTransactionAmount
            FROM sync.ProductSaleInformation
            WHERE tenant_id = ? AND store_id = ?
              AND CAST(TransactionDate AS DATE) BETWEEN ? AND ?
            GROUP BY DiscountPercentage
        ), WithTotal AS (
            SELECT DiscountPercentage, TotalTransactionAmount,
                   SUM(TotalTransactionAmount) OVER () AS TotalSalesAmount
            FROM DiscountSummary
        )
        SELECT
            CASE WHEN DiscountPercentage IS NULL THEN 'Total'
                 ELSE CONCAT(CAST(DiscountPercentage AS VARCHAR(20)), '%') END AS Discount,
            CAST(ROUND(SUM(TotalTransactionAmount), 2) AS DECIMAL(18,2)) AS Amount,
            CASE WHEN GROUPING(DiscountPercentage) = 1 THEN 100
                 WHEN MAX(TotalSalesAmount) = 0 THEN 0
                 ELSE CAST(ROUND((SUM(TotalTransactionAmount) / MAX(TotalSalesAmount)) * 100, 0) AS INT)
            END AS Percentage
        FROM WithTotal
        GROUP BY ROLLUP(DiscountPercentage)
        ORDER BY CASE WHEN DiscountPercentage IS NULL THEN 1 ELSE 0 END, DiscountPercentage
    """
    return _run(sql, (tenant_id, store_id, from_date, to_date))


# ---------------------------------------------------------------------------
# 3. Monthly Sales Report  (legacy GenerateMonthlyReport)
#    Legacy pivoted saleinformation.Billamount by SeriesName; sync.SaleInformation
#    carries no SeriesName, so we derive the day/series matrix from
#    ProductSaleInformation.Transactionamount (single synced source of truth).
# ---------------------------------------------------------------------------

def monthly_sales(tenant_id, store_id, from_date, to_date):
    sql = """
        SELECT
            CAST(TransactionDate AS DATE) AS ReportDate,
            SeriesName,
            SUM(Transactionamount)        AS Amount
        FROM sync.ProductSaleInformation
        WHERE tenant_id = ? AND store_id = ?
          AND CAST(TransactionDate AS DATE) BETWEEN ? AND ?
          AND TransactionValidity = 0
        GROUP BY CAST(TransactionDate AS DATE), SeriesName
        ORDER BY ReportDate
    """
    return _run(sql, (tenant_id, store_id, from_date, to_date))


# ---------------------------------------------------------------------------
# 4. Margin Report  (legacy GenerateMarginReport)
# ---------------------------------------------------------------------------

def margin(tenant_id, store_id, from_date, to_date):
    sql = """
        SELECT
            RTRIM(seriesname) AS SeriesName,
            CAST(ROUND(SUM(Transactionamount), 0) AS INT)                      AS TotalTransactionAmount,
            CAST(ROUND(SUM(CostOfSales), 0) AS INT)                           AS TotalItemCost,
            CAST(ROUND(SUM(Quantity), 0) AS INT)                              AS TotalQuantity,
            COUNT(DISTINCT BillNumber)                                        AS NumberOfBills,
            CAST(ROUND(SUM(Transactionamount) - SUM(CostOfSales), 0) AS INT)   AS ProfitValue,
            CASE
                WHEN SUM(CostOfSales) = 0 OR SUM(Transactionamount) = 0 THEN 0
                ELSE CAST(ROUND(((SUM(Transactionamount)) - SUM(CostOfSales)) / SUM(CostOfSales) * 100, 0) AS INT)
            END AS MarginPercentage
        FROM sync.ProductSaleInformation
        WHERE tenant_id = ? AND store_id = ?
          AND CAST(TransactionDate AS DATE) BETWEEN ? AND ?
          AND seriesname NOT IN ('n', 'sa', 'er')
          AND TransactionValidity = 0
        GROUP BY seriesname
        ORDER BY seriesname ASC
    """
    return _run(sql, (tenant_id, store_id, from_date, to_date))


# ---------------------------------------------------------------------------
# 5. Daily Margin Report  (legacy DailyMarginReport)
# ---------------------------------------------------------------------------

def daily_margin(tenant_id, store_id, from_date, to_date):
    sql = """
        SELECT
            CONVERT(VARCHAR(10), CONVERT(DATE, TransactionDate), 105) AS ReportDate,
            ISNULL(ROUND(SUM(CASE WHEN seriesname = 'C' THEN Transactionamount END), 2), 0) AS C_Bills,
            ISNULL(ROUND(SUM(CASE WHEN seriesname = 'M' THEN Transactionamount END), 2), 0) AS M_Bills,
            ISNULL(ROUND(SUM(CASE WHEN seriesname = 'R' THEN Transactionamount END), 2), 0) AS R_Bills,
            ISNULL(ROUND(SUM(CASE WHEN seriesname = 'W' THEN Transactionamount END), 2), 0) AS W_Bills,
            ISNULL(ROUND(SUM(CASE WHEN seriesname NOT IN ('C','M','R','W','n','sa','er') THEN Transactionamount END), 2), 0) AS Other_Txn,
            ISNULL(ROUND(SUM(Transactionamount), 2), 0) AS TransactionAmount,
            ISNULL(ROUND(SUM(CostOfSales), 2), 0)       AS TotalItemCost,
            ISNULL(ROUND(SUM(Transactionamount) - SUM(CostOfSales), 2), 0) AS ProfitValue,
            ISNULL(ROUND(
                CASE WHEN SUM(CASE WHEN seriesname = 'C' THEN CostOfSales END) = 0 THEN 0
                ELSE (SUM(CASE WHEN seriesname = 'C' THEN Transactionamount END) - SUM(CASE WHEN seriesname = 'C' THEN CostOfSales END))
                     / SUM(CASE WHEN seriesname = 'C' THEN CostOfSales END) * 100 END, 2), 0) AS C_Margin_Pct
        FROM sync.ProductSaleInformation
        WHERE tenant_id = ? AND store_id = ?
          AND CAST(TransactionDate AS DATE) BETWEEN ? AND ?
          AND seriesname NOT IN ('n','sa','er')
          AND TransactionValidity = 0
        GROUP BY CONVERT(DATE, TransactionDate)
        ORDER BY CONVERT(DATE, TransactionDate) ASC
    """
    return _run(sql, (tenant_id, store_id, from_date, to_date))


# ---------------------------------------------------------------------------
# Non-Moving family (legacy LoadNMReport / LoadNMNSReport). `having_clause`
# selects between "not sold for N days" and "purchased but never sold".
# ---------------------------------------------------------------------------

_NM_SELECT = """
    SELECT
        s.suppliername                        AS SupplierName,
        p.SubLocation,
        pt.ProductCode,
        p.ProductName,
        p.TotalStock,
        b.Stock                               AS Batch_Stock,
        ROUND(p.TotalStock / NULLIF(p.SaleUnit, 0), 0) AS StripQty,
        b.ExpiryDate,
        MAX(p.SaleUnit)                       AS SaleUnit,
        MAX(p.PurchasePrice)                  AS PurchasePrice,
        MAX(p.MRP)                            AS MRP,
        p.UnitDescription                     AS UnitDesc,
        MAX(pt.LastBillDate)                  AS LastBillDate,
        MAX(pt.LastGrnDate)                   AS LastGRNDate,
        DATEDIFF(DAY, MAX(pt.LastBillDate), GETDATE()) AS SalesAge,
        DATEDIFF(DAY, MAX(pt.LastGrnDate), GETDATE())  AS PurAge
    FROM sync.Products p
    INNER JOIN sync.ProductTrans pt
        ON pt.tenant_id = p.tenant_id AND pt.store_id = p.store_id AND pt.ProductCode = p.ProductCode
    INNER JOIN sync.Batches b
        ON b.tenant_id = p.tenant_id AND b.store_id = p.store_id AND b.ProductCode = p.ProductCode
    INNER JOIN sync.Suppliers s
        ON s.tenant_id = b.tenant_id AND s.store_id = b.store_id AND s.suppliercode = b.SupplierCode
    WHERE p.tenant_id = ? AND p.store_id = ?
      AND p.TotalStock > 0 AND p.isActive = 1 AND b.Stock > 0
"""

_NM_GROUP = """
    GROUP BY pt.ProductCode, p.ProductName, p.TotalStock, p.SaleUnit,
             p.PurchasePrice, p.MRP, p.UnitDescription, p.SubLocation,
             b.ExpiryDate, b.Stock, s.suppliername
"""


def _nm_query(tenant_id, store_id, dwell_days, supplier_code, having, order_by):
    sql = _NM_SELECT
    params = [tenant_id, store_id]
    if supplier_code:
        sql += " AND b.SupplierCode = ? "
        params.append(supplier_code)
    sql += _NM_GROUP + having + order_by
    params.append(int(dwell_days))
    return _run(sql, tuple(params))


def non_moving(tenant_id, store_id, dwell_days, supplier_code=None):
    return _nm_query(
        tenant_id, store_id, dwell_days, supplier_code,
        having=" HAVING (DATEDIFF(DAY, MAX(pt.LastBillDate), GETDATE()) > ? OR MAX(pt.LastBillDate) IS NULL) ",
        order_by=" ORDER BY p.ProductName ",
    )


def purchased_not_sold(tenant_id, store_id, dwell_days, supplier_code=None):
    return _nm_query(
        tenant_id, store_id, dwell_days, supplier_code,
        having=" HAVING (MAX(pt.LastBillDate) IS NULL AND DATEDIFF(DAY, MAX(pt.LastGrnDate), GETDATE()) < ?) ",
        order_by=" ORDER BY s.suppliername, p.ProductName ",
    )


def non_moving_highlights(tenant_id, store_id, dwell_days, min_pur_age=10, limit=50):
    """Lean variant of non_moving(): pushes the PurAge filter and a TOP N cap
    into SQL so callers that only need a handful of high-value rows (e.g. a
    rotating highlight panel) don't pay for the full unfiltered report."""
    sql = _NM_SELECT.replace("SELECT", "SELECT TOP (%d)" % int(limit), 1)
    sql += _NM_GROUP
    sql += """
        HAVING (DATEDIFF(DAY, MAX(pt.LastBillDate), GETDATE()) > ? OR MAX(pt.LastBillDate) IS NULL)
           AND DATEDIFF(DAY, MAX(pt.LastGrnDate), GETDATE()) >= ?
        ORDER BY (p.TotalStock * ISNULL(MAX(p.MRP), 0)) DESC
    """
    params = (tenant_id, store_id, int(dwell_days), int(min_pur_age))
    return _run(sql, params)


# ---------------------------------------------------------------------------
# 8. EYRUS — 7-day sales summary  (legacy Generate7DaySalesSummaryReport)
#    Dynamic day columns for the trailing 7 days (server-generated dates → safe
#    to inline into column names); division_code stays parameterized.
# ---------------------------------------------------------------------------

def eyrus_7day(tenant_id, store_id, division_code):
    days = [date.today() - timedelta(days=i) for i in range(6, -1, -1)]
    day_cols = ",\n".join(
        "ISNULL(SUM(CASE WHEN CAST(s.TransactionDate AS DATE) = '%s' THEN s.Quantity ELSE 0 END), 0) AS [%s]"
        % (d.strftime("%Y-%m-%d"), d.strftime("%b %d"))
        for d in days
    )
    sql = f"""
        SELECT
            p.ProductCode,
            p.ProductName,
            {day_cols},
            ISNULL(SUM(s.Quantity), 0)  AS SaleQty,
            ISNULL(MAX(p.TotalStock), 0) AS Stock
        FROM sync.Products p
        LEFT JOIN sync.ProductSaleInformation s
            ON s.tenant_id = p.tenant_id AND s.store_id = p.store_id
           AND s.ProductCode = p.ProductCode
           AND CAST(s.TransactionDate AS DATE) BETWEEN ? AND ?
        WHERE p.tenant_id = ? AND p.store_id = ? AND p.DivisionCode = ?
        GROUP BY p.ProductCode, p.ProductName
        ORDER BY p.ProductName
    """
    return _run(sql, (days[0], days[-1], tenant_id, store_id, division_code))
