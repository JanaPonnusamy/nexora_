"""Data access for the Expiry Stock (Cutting Expiry) report — read-only over
the synced Shopaid batch stock in NEXORA_PLATFORM.

This is the on-hand near-expiry stock listing (the legacy Shopaid "Expiry
List" screen), NOT the supplier given/received report. It is a faithful port
of dbo.dsp_ExpiryListForReturn: in-stock batches joined to their product,
filtered by supplier + expiry-date window, with the tax description looked up
from sync.TAX.  Every batch whose remaining stock is less than one sale unit
is flagged "Cutting" (a loose / part-strip about to expire).

Batch stock, MRP, expiry, cost, PTR, sale-unit and sub-location all come from
sync.Batches; product name / unit / total stock / main supplier from
sync.Products; supplier name from sync.Suppliers; tax label from sync.TAX.

Every query is scoped by tenant_id + store_id.
"""

from config.database import get_connection


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


# Effective sale unit for the cutting test: batch sale-unit, else product
# sale-unit, else 1. A batch is "cutting" when its remaining stock is below
# one sale unit (a broken / loose pack).
_SALE_UNIT = ("ISNULL(NULLIF(b.SaleUnit,0), ISNULL(NULLIF(pr.SaleUnit,0), 1))")


def suppliers(tenant_id, store_id):
    """Suppliers that currently have in-stock batches at the store — used to
    populate the supplier filter (main product supplier, matching legacy)."""
    sql = """
        SELECT DISTINCT
            CAST(pr.SupplierCode AS VARCHAR(50)) AS SupplierCode,
            RTRIM(COALESCE(s.suppliername, CAST(pr.SupplierCode AS VARCHAR(50)))) AS SupplierName
        FROM sync.Batches b
        INNER JOIN sync.Products pr
            ON pr.tenant_id = b.tenant_id AND pr.store_id = b.store_id
           AND pr.ProductCode = b.ProductCode
        LEFT JOIN sync.Suppliers s
            ON s.tenant_id = pr.tenant_id AND s.store_id = pr.store_id
           AND s.suppliercode = pr.SupplierCode
        WHERE b.tenant_id = ? AND b.store_id = ? AND b.Stock <> 0
          AND pr.SupplierCode IS NOT NULL AND RTRIM(pr.SupplierCode) <> ''
        ORDER BY SupplierName
    """
    return _run(sql, (tenant_id, store_id))


def report(tenant_id, store_id, supplier_code=None, exp_from=None, exp_to=None,
           only_cutting=False):
    """In-stock batches for the store, filtered by supplier + expiry window."""
    where = ["b.tenant_id = ?", "b.store_id = ?", "b.Stock <> 0",
             "ISNULL(pr.isActive, 1) = 1"]
    params = [tenant_id, store_id]
    if supplier_code:
        where.append("pr.SupplierCode = ?")
        params.append(supplier_code)
    if exp_from:
        where.append("CAST(b.ExpiryDate AS DATE) >= ?")
        params.append(exp_from)
    if exp_to:
        where.append("CAST(b.ExpiryDate AS DATE) <= ?")
        params.append(exp_to)
    if only_cutting:
        where.append(f"b.Stock < {_SALE_UNIT}")

    sql = f"""
        SELECT
            b.ProductCode                                       AS ProductCode,
            pr.ProductName                                      AS ProductName,
            pr.UnitDescription                                  AS UnitDescription,
            ISNULL(NULLIF(b.SubLocation, ''), pr.SubLocation)   AS Loc,
            pr.TotalStock                                       AS TotalStock,
            b.Stock                                             AS BatchStock,
            COALESCE(NULLIF(b.BatchDescription, ''),
                     CAST(b.BatchCode AS VARCHAR(20)))          AS Batch,
            b.ExpiryDate                                        AS ExpiryDate,
            b.MRP                                               AS MRP,
            DATEDIFF(DAY, b.ExpiryDate, CAST(GETDATE() AS DATE)) AS DaysExpired,
            CASE WHEN b.Stock < {_SALE_UNIT} THEN 1 ELSE 0 END  AS Cutting,
            b.ItemCost                                          AS Cost,
            b.PurchasePrice                                     AS PTR,
            st.description                                      AS Tax,
            RTRIM(COALESCE(sup.suppliername,
                           CAST(pr.SupplierCode AS VARCHAR(50)))) AS Supplier
        FROM sync.Batches b
        INNER JOIN sync.Products pr
            ON pr.tenant_id = b.tenant_id AND pr.store_id = b.store_id
           AND pr.ProductCode = b.ProductCode
        LEFT JOIN sync.TAX st
            ON st.tenant_id = b.tenant_id AND st.store_id = b.store_id
           AND st.taxcode = b.SalesTaxCode
        LEFT JOIN sync.Suppliers sup
            ON sup.tenant_id = pr.tenant_id AND sup.store_id = pr.store_id
           AND sup.suppliercode = pr.SupplierCode
        WHERE {' AND '.join(where)}
        ORDER BY b.ExpiryDate, pr.ProductName, Batch
    """
    return _run(sql, tuple(params))


def date_bounds(tenant_id, store_id):
    """Oldest / newest expiry date among in-stock batches (for filter defaults)."""
    sql = """
        SELECT MIN(CAST(ExpiryDate AS DATE)) AS Oldest,
               MAX(CAST(ExpiryDate AS DATE)) AS Newest
        FROM sync.Batches
        WHERE tenant_id = ? AND store_id = ? AND Stock <> 0
    """
    _, rows = _run(sql, (tenant_id, store_id))
    o = rows[0]["Oldest"] if rows else None
    n = rows[0]["Newest"] if rows else None
    return {
        "oldest": o.strftime("%Y-%m-%d") if o else None,
        "newest": n.strftime("%Y-%m-%d") if n else None,
    }
