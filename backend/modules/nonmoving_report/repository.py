"""Data access for the Non-Moving (dwell-days) Stock Report — read-only over
the synced Shopaid batch data in NEXORA_PLATFORM.

Faithful port of the legacy stored procedure
``dbo.Dsp_NonMovingStockPeriodItemSupplierName`` (@ProcessMode not used; the
non-moving report reads the batch master directly). The legacy engine is the
view ``Dvw_MasterBatches`` = ``Batches UNION H_Batches``; for stock-on-hand
non-moving we read current ``sync.Batches`` (H_Batches is archived / zero-stock).

Definition of "non-moving": a batch still holding stock that was received on or
after its last sale (``LastSaleDate <= LastReceivedDate`` — i.e. it has not sold
since it came in) and whose dwell age falls in the requested day range.

  basis = 'sold'     (ReportMode 0): Days = days since LastSaleDate
  basis = 'received' (ReportMode 1): Days = days since LastReceivedDate

Given/Sale valuations come from the batch snapshot columns
``GrsStkValueatCost`` / ``GrsStkValueatSale`` (COALESCE 0 until a store re-syncs
them). Validated to the penny against the SP for NMA (basis=sold, >=90 days:
74 rows / cost 10,247.57 / sale 16,335.08).

Every query is tenant-scoped (+ store_id when a single store is chosen).
"""

from config.database import get_connection

_BIG_DAYS = 999999


def _run(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()


def data(tenant_id, store_id, basis, min_days, max_days, include_nil,
         supplier_code, supplier_mode):
    """Non-moving batch rows for the scope. ``supplier_mode`` 0 = product's
    supplier (Products.SupplierCode), 1 = batch's actual supplier
    (Batches.SupplierCode)."""
    rm = 0 if (basis or "sold") == "sold" else 1
    t = int(min_days or 0)
    f = int(max_days) if max_days not in (None, "", 0) else _BIG_DAYS
    if f < t:
        f = _BIG_DAYS

    # Supplier column depends on the chosen mode.
    supp_code = "p.SupplierCode" if supplier_mode != 1 else "b.SupplierCode"

    where = ["p.isActive = 1", "b.tenant_id = ?"]
    params = [tenant_id]
    if store_id:
        where.append("b.store_id = ?")
        params.append(store_id)
    if not include_nil:
        where.append("ISNULL(b.Stock, 0) <> 0")
    # Core non-moving gate (applies to both bases).
    where.append("b.LastSaleDate <= b.LastReceivedDate")

    if rm == 0:
        where.append("DATEDIFF(d, b.LastSaleDate, CAST(GETDATE() AS DATE)) BETWEEN ? AND ?")
        params += [t, f]
        days_expr = "DATEDIFF(d, b.LastSaleDate, CAST(GETDATE() AS DATE))"
    else:
        where.append("b.LastSaleDate IS NOT NULL")
        where.append("DATEDIFF(d, b.LastSaleDate, CAST(GETDATE() AS DATE)) > ?")
        where.append("DATEDIFF(d, b.LastReceivedDate, CAST(GETDATE() AS DATE)) BETWEEN ? AND ?")
        params += [t, t, f]
        days_expr = "DATEDIFF(d, b.LastReceivedDate, CAST(GETDATE() AS DATE))"

    if supplier_code:
        where.append(f"{supp_code} = ?")
        params.append(supplier_code)

    sql = f"""
        SELECT
            CAST({supp_code} AS VARCHAR(50))        AS SupplierCode,
            RTRIM(COALESCE(s.suppliername, CAST({supp_code} AS VARCHAR(50)))) AS SupplierName,
            b.ProductCode                            AS ProductCode,
            p.ProductName                            AS ProductName,
            p.PackageInformation                     AS Pack,
            b.Stock                                  AS Stock,
            b.BatchDescription                       AS Batch,
            b.ExpiryDate                             AS ExpiryDate,
            b.LastReceivedDate                       AS ReceivedDate,
            b.LastSaleDate                           AS LastSoldDate,
            {days_expr}                              AS Days,
            b.GrnNumber                              AS GrnNumber,
            b.InvoiceNumber                          AS InvoiceNumber,
            b.SubLocation                            AS Rack,
            b.PurchasePrice                          AS PurchasePrice,
            b.SalePrice                              AS SalePrice,
            b.MRP                                    AS MRP,
            ISNULL(b.GrsStkValueatCost, 0)           AS CostValue,
            ISNULL(b.GrsStkValueatSale, 0)           AS SaleValue
        FROM sync.Batches b
        INNER JOIN sync.Products p
            ON p.tenant_id = b.tenant_id AND p.store_id = b.store_id
           AND p.ProductCode = b.ProductCode
        LEFT JOIN sync.Suppliers s
            ON s.tenant_id = b.tenant_id AND s.store_id = b.store_id
           AND s.suppliercode = {supp_code}
        WHERE {' AND '.join(where)}
        ORDER BY Days DESC, SupplierName, p.ProductName
    """
    _, rows = _run(sql, tuple(params))
    return rows


def suppliers(tenant_id, store_id=None, supplier_mode=0):
    """Distinct suppliers with non-nil-stock batches in the scope — for the
    filter dropdown."""
    supp_code = "p.SupplierCode" if supplier_mode != 1 else "b.SupplierCode"
    where = ["b.tenant_id = ?", "ISNULL(b.Stock,0) <> 0", f"{supp_code} IS NOT NULL"]
    params = [tenant_id]
    if store_id:
        where.append("b.store_id = ?")
        params.append(store_id)
    sql = f"""
        WITH codes AS (
            SELECT DISTINCT CAST({supp_code} AS VARCHAR(50)) AS SupplierCode
            FROM sync.Batches b
            INNER JOIN sync.Products p
                ON p.tenant_id = b.tenant_id AND p.store_id = b.store_id
               AND p.ProductCode = b.ProductCode
            WHERE {' AND '.join(where)}
        )
        SELECT c.SupplierCode,
               RTRIM(COALESCE(MAX(s.suppliername), c.SupplierCode)) AS SupplierName
        FROM codes c
        LEFT JOIN sync.Suppliers s
            ON s.suppliercode = c.SupplierCode AND s.tenant_id = ?
        GROUP BY c.SupplierCode
        ORDER BY SupplierName
    """
    params.append(tenant_id)
    _, rows = _run(sql, tuple(params))
    return rows
