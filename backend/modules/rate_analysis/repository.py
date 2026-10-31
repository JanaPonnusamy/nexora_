"""Data access for Rate Analysis — read-only over the synced Shopaid tables in
NEXORA_PLATFORM (sync.PurchaseTrans / sync.ProductSaleInformation /
sync.Products / sync.Suppliers). Every query is tenant-scoped.

Units: PurchaseTrans quantities and PTR are per purchase unit (strip / pack);
ProductSaleInformation.Quantity is in loose units, so callers divide by
Products.SaleUnit (packing per strip) to get strips.
"""

from config.database import get_connection


def _rows(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def tenant_stores(tenant_id, include_warehouse=False):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT CAST(store_id AS VARCHAR(36)) AS store_id, store_code, store_name,
                      CAST(ISNULL(is_warehouse, 0) AS INT) AS is_warehouse
                 FROM dbo.stores
                WHERE tenant_id = ? AND ISNULL(is_active, 1) = 1
                  AND (? = 1 OR ISNULL(is_warehouse, 0) = 0)
                ORDER BY ISNULL(store_order, 999), store_code""",
            tenant_id, 1 if include_warehouse else 0)
        return _rows(cur)
    finally:
        conn.close()


def _load_codes(cur, codes):
    cur.execute("CREATE TABLE #rc (store_id UNIQUEIDENTIFIER, ProductCode INT, PRIMARY KEY (store_id, ProductCode))")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO #rc VALUES (?, ?)", codes)


def purchase_lines(tenant_id, store_ids, date_from, date_to, codes=None):
    """Supplier purchase (IV) lines in [date_from, date_to) for the stores,
    optionally limited to (store_id, product_code) pairs. Transfers (TI) and
    returns are excluded — IV series only."""
    if not store_ids:
        return []
    ph = ",".join("?" * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        join = ""
        if codes is not None:
            codes = list({(str(s).upper(), int(c)) for s, c in codes})
            if not codes:
                return []
            _load_codes(cur, codes)
            join = "JOIN #rc ON #rc.store_id = t.store_id AND #rc.ProductCode = t.ProductCode"
        cur.execute(
            f"""SELECT CAST(t.store_id AS VARCHAR(36)) AS store_id, t.ProductCode AS product_code,
                       RTRIM(p.ProductName) AS product_name, ISNULL(p.SaleUnit, 1) AS sale_unit,
                       RTRIM(ISNULL(sp.suppliername, t.SupplierCode)) AS supplier_name,
                       UPPER(RTRIM(LTRIM(ISNULL(sp.GSTNumber, '')))) AS gst,
                       RTRIM(t.SupplierCode) AS supplier_code,
                       t.grndate AS grn_date, t.Grnnumber AS grn_no, t.mrp,
                       t.stockreceived AS qty, ISNULL(t.FreeQty, 0) AS free_qty,
                       t.purchaseprice AS ptr, ISNULL(t.ProductDiscPercent, 0) AS disc_pct
                  FROM sync.PurchaseTrans t
                  {join}
                  JOIN sync.Products p ON p.store_id = t.store_id AND p.ProductCode = t.ProductCode
                  LEFT JOIN sync.Suppliers sp ON sp.store_id = t.store_id AND sp.suppliercode = t.SupplierCode
                 WHERE t.tenant_id = ? AND t.store_id IN ({ph})
                   AND t.InvoiceSeries = 'IV' AND t.grndate >= ? AND t.grndate < ?
                   AND t.purchaseprice > 0 AND t.stockreceived > 0""",
            tenant_id, *store_ids, date_from, date_to)
        return _rows(cur)
    finally:
        conn.close()


def all_products(tenant_id, store_ids):
    """Every product of the stores (name, pack, MRP) — the service groups
    them across stores by normalised name, since product codes are store-local."""
    if not store_ids:
        return []
    ph = ",".join("?" * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT CAST(p.store_id AS VARCHAR(36)) AS store_id, p.ProductCode AS product_code,
                       RTRIM(p.ProductName) AS product_name, ISNULL(p.SaleUnit, 1) AS sale_unit, p.MRP AS mrp
                  FROM sync.Products p
                 WHERE p.tenant_id = ? AND p.store_id IN ({ph}) AND p.ProductName IS NOT NULL""",
            tenant_id, *store_ids)
        return _rows(cur)
    finally:
        conn.close()


def sales_qty(codes, date_from, date_to):
    """Loose-unit sales per (store_id, product_code) — same filters as the
    order engine: sales series, valid, not flagged DontConsiderInOrder."""
    codes = list({(str(s).upper(), int(c)) for s, c in codes})
    if not codes:
        return {}
    conn = get_connection()
    try:
        cur = conn.cursor()
        _load_codes(cur, codes)
        cur.execute(
            """SELECT CAST(x.store_id AS VARCHAR(36)), x.ProductCode, SUM(x.Quantity)
                 FROM sync.ProductSaleInformation x
                 JOIN #rc ON #rc.store_id = x.store_id AND #rc.ProductCode = x.ProductCode
                WHERE x.SeriesTransID = 1 AND x.TransactionValidity = 0
                  AND ISNULL(x.DontConsiderInOrder, 0) = 0
                  AND x.TransactionDate >= ? AND x.TransactionDate < ?
                GROUP BY x.store_id, x.ProductCode""",
            date_from, date_to)
        return {(s.upper(), int(c)): float(q or 0) for s, c, q in cur.fetchall()}
    finally:
        conn.close()
