"""Reads for the Non-Moving Stock Analysis workspace (Stock Client
"Non-Moving Stock") -- read-only over the synced POS data in NEXORA_PLATFORM.

One bulk query per store (never per product) returns every product that holds
stock or sold in the last 180 days, with everything the analysis needs:

  stock          the store's authoritative stock (_dbutil.store_stock_expr =
                 latest ProductTrans.StockInHand, owner ruling) and, separately,
                 the sum of positive batch stock -- the two are compared, never
                 silently merged.
  valuation      from the in-stock batches, three separate measures:
                   cost  = Batches.GrsStkValueatCost (the POS's own stock value
                           at cost = Stock x ItemCost / SaleUnit; the POS uses
                           the PTR when a batch has no ItemCost). Validated:
                           matches the computed value on 99.8% of batches and
                           the legacy SP report to the penny (NMA).
                   ptr   = Stock x PurchasePrice / SaleUnit
                   mrp   = Stock x MRP / SaleUnit
                 Stock is in loose units, prices per pack -- hence / SaleUnit
                 (raw Stock x ItemCost overstates retail stock ~7x).
  last sale      three sources, kept apart so the service can say which one
                 it used:
                   psi     MAX(TransactionDate) of a valid sale line -- legacy
                           rule SeriesTransID = 1, TransactionValidity = 0,
                           Quantity > 0 (order_local.sql). A warehouse also
                           moves stock by Transfer-Out (SeriesTransID = 11,
                           owner ruling, see legacy_order warehouse order).
                           Synced PSI history starts 2025-04-01.
                   rollup  MAX(ProductTrans.LastBillDate) -- the POS's own last
                           bill date, reaches back years (matches psi on 99.2%
                           of products), so it covers sales before PSI history.
                   batch   MAX(Batches.LastSaleDate).
  sales          net valid sale qty in the last 30 / 90 / 180 days (in-bill
                 return lines net off), and the count of INVALID (cancelled)
                 sale lines in 180 days, for transparency.
  purchases      last supplier purchase (InvoiceSeries <> 'TI'; TI = internal
                 transfer, its SupplierCode collides with real suppliers),
                 last GRN of any kind (incl. transfers in), first receipt.
  expiry         expired / near-expiry stock (qty + cost) and earliest expiry.

Every query is tenant- and store-scoped.
"""

from datetime import date, timedelta

from config.database import get_connection
from modules.procurement._dbutil import (
    rows_to_dicts as _rows_to_dicts,
    store_stock_expr as _store_stock_expr,
    stringify as _stringify,
)
from modules.procurement.intelligence_repository import _floatify


def store_snapshot(tenant_id, store_id, warehouse=False, near_expiry_days=90):
    """Every product of one store that holds stock (product or batch level) or
    sold in the last 180 days, with stock, valuation, sales, purchase and
    expiry facts (see module docstring)."""
    today = date.today()
    d30, d90, d180 = (today - timedelta(days=n) for n in (30, 90, 180))
    near = today + timedelta(days=int(near_expiry_days))
    series = "(1, 11)" if warehouse else "(1)"
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Each aggregate is materialised into a temp table first: as one CTE
        # statement the optimiser picked a plan ~3x slower than its parts.
        cur.execute(
            f"""
            SET NOCOUNT ON;
            DECLARE @t UNIQUEIDENTIFIER = ?, @s UNIQUEIDENTIFIER = ?;
            DECLARE @d30 DATE = ?, @d90 DATE = ?, @d180 DATE = ?, @today DATE = ?, @near DATE = ?;

            SELECT ProductCode,
                   MAX(CASE WHEN ISNULL(TransactionValidity, 0) = 0 AND Quantity > 0
                            THEN TransactionDate END)                                     AS last_sale_psi,
                   SUM(CASE WHEN ISNULL(TransactionValidity, 0) = 0 AND TransactionDate >= @d30
                            THEN Quantity ELSE 0 END)                                     AS sales_30,
                   SUM(CASE WHEN ISNULL(TransactionValidity, 0) = 0 AND TransactionDate >= @d90
                            THEN Quantity ELSE 0 END)                                     AS sales_90,
                   SUM(CASE WHEN ISNULL(TransactionValidity, 0) = 0 THEN Quantity ELSE 0 END) AS sales_180,
                   COUNT(DISTINCT CASE WHEN ISNULL(TransactionValidity, 0) = 0 AND Quantity > 0
                                        AND TransactionDate >= @d90 THEN Bnumber END)    AS bills_90,
                   SUM(CASE WHEN ISNULL(TransactionValidity, 0) <> 0 THEN 1 ELSE 0 END)   AS invalid_lines_180
            INTO #sale
            FROM sync.ProductSaleInformation
            WHERE tenant_id = @t AND store_id = @s AND SeriesTransID IN {series}
              AND TransactionDate >= @d180
            GROUP BY ProductCode;

            -- Last valid sale before the 180-day window (PSI history only).
            SELECT ProductCode, MAX(TransactionDate) AS last_sale_psi
            INTO #old
            FROM sync.ProductSaleInformation
            WHERE tenant_id = @t AND store_id = @s AND SeriesTransID IN {series}
              AND ISNULL(TransactionValidity, 0) = 0 AND Quantity > 0
              AND TransactionDate < @d180
            GROUP BY ProductCode;

            SELECT ProductCode, MAX(LastBillDate) AS last_sale_rollup
            INTO #roll
            FROM sync.ProductTrans
            WHERE tenant_id = @t AND store_id = @s
            GROUP BY ProductCode;

            SELECT ProductCode, Stock, ExpiryDate, LastSaleDate, GrnDate, LastReceivedDate,
                   COALESCE(GrsStkValueatCost,
                            Stock * COALESCE(NULLIF(ItemCost, 0), PurchasePrice) / NULLIF(SaleUnit, 0), 0) AS cost,
                   ISNULL(Stock * PurchasePrice / NULLIF(SaleUnit, 0), 0) AS ptrv,
                   ISNULL(Stock * MRP / NULLIF(SaleUnit, 0), 0)           AS mrpv
            INTO #b
            FROM sync.Batches
            WHERE tenant_id = @t AND store_id = @s;

            SELECT ProductCode,
                   SUM(CASE WHEN Stock > 0 THEN Stock ELSE 0 END)                         AS batch_stock,
                   SUM(CASE WHEN Stock > 0 THEN 1 ELSE 0 END)                             AS batch_count,
                   SUM(CASE WHEN Stock > 0 THEN cost ELSE 0 END)                          AS cost_value,
                   SUM(CASE WHEN Stock > 0 THEN ptrv ELSE 0 END)                          AS ptr_value,
                   SUM(CASE WHEN Stock > 0 THEN mrpv ELSE 0 END)                          AS mrp_value,
                   SUM(CASE WHEN Stock > 0 AND ExpiryDate < @today THEN Stock ELSE 0 END) AS expired_qty,
                   SUM(CASE WHEN Stock > 0 AND ExpiryDate < @today THEN cost ELSE 0 END)  AS expired_value,
                   SUM(CASE WHEN Stock > 0 AND ExpiryDate >= @today AND ExpiryDate < @near
                            THEN Stock ELSE 0 END)                                        AS near_expiry_qty,
                   SUM(CASE WHEN Stock > 0 AND ExpiryDate >= @today AND ExpiryDate < @near
                            THEN cost ELSE 0 END)                                         AS near_expiry_value,
                   SUM(CASE WHEN Stock > 0 AND ExpiryDate IS NULL THEN 1 ELSE 0 END)      AS no_expiry_batches,
                   MIN(CASE WHEN Stock > 0 THEN ExpiryDate END)                           AS earliest_expiry,
                   MAX(LastSaleDate)                                                      AS last_sale_batch,
                   MIN(COALESCE(GrnDate, LastReceivedDate))                               AS first_batch_date
            INTO #bat
            FROM #b
            GROUP BY ProductCode;

            SELECT ProductCode, grndate, ID, InvoiceSeries, CAST(SupplierCode AS VARCHAR(100)) AS supplier_code
            INTO #pt
            FROM sync.PurchaseTrans
            WHERE tenant_id = @t AND store_id = @s;

            SELECT ProductCode,
                   MAX(CASE WHEN ISNULL(InvoiceSeries, '') <> 'TI' THEN grndate END) AS last_purchase_date,
                   MAX(grndate)                                                     AS last_grn_date,
                   MIN(grndate)                                                     AS first_grn_date
            INTO #pur
            FROM #pt
            GROUP BY ProductCode;

            SELECT ProductCode, supplier_code
            INTO #sup
            FROM (SELECT ProductCode, supplier_code,
                         ROW_NUMBER() OVER (PARTITION BY ProductCode ORDER BY grndate DESC, ID DESC) AS rn
                  FROM #pt
                  WHERE ISNULL(InvoiceSeries, '') <> 'TI' AND supplier_code IS NOT NULL) x
            WHERE rn = 1;

            SELECT CAST(suppliercode AS VARCHAR(100)) AS code, MAX(suppliername) AS suppliername
            INTO #sn
            FROM sync.Suppliers
            WHERE tenant_id = @t AND store_id = @s AND suppliercode IS NOT NULL
            GROUP BY CAST(suppliercode AS VARCHAR(100));
            CREATE UNIQUE CLUSTERED INDEX ix ON #sn (code);

            SELECT p.ProductCode, p.ProductName, p.UnitDescription, p.PackageInformation, p.SaleUnit,
                   p.ProductType, p.isActive, p.CreationDate, p.MRP, p.SupplierCode,
                   CAST({_store_stock_expr("p")} AS DECIMAL(18,3)) AS stock
            INTO #base
            FROM sync.Products p
            WHERE p.tenant_id = @t AND p.store_id = @s;

            SELECT CAST(b.ProductCode AS VARCHAR(100))           AS product_code,
                   RTRIM(b.ProductName)                          AS product_name,
                   RTRIM(b.UnitDescription)                      AS unit,
                   RTRIM(b.PackageInformation)                   AS pack,
                   b.SaleUnit                                    AS sale_unit,
                   b.ProductType                                 AS product_type,
                   b.isActive                                    AS is_active,
                   b.CreationDate                                AS created_date,
                   b.MRP                                         AS mrp,
                   b.stock                                       AS stock,
                   bat.batch_stock, bat.batch_count, bat.cost_value, bat.ptr_value, bat.mrp_value,
                   bat.expired_qty, bat.expired_value, bat.near_expiry_qty, bat.near_expiry_value,
                   bat.no_expiry_batches, bat.earliest_expiry,
                   COALESCE(sale.last_sale_psi, old.last_sale_psi) AS last_sale_psi,
                   roll.last_sale_rollup,
                   bat.last_sale_batch,
                   sale.sales_30, sale.sales_90, sale.sales_180, sale.bills_90, sale.invalid_lines_180,
                   pur.last_purchase_date, pur.last_grn_date,
                   COALESCE(pur.first_grn_date, bat.first_batch_date) AS first_receipt_date,
                   COALESCE(sup.supplier_code, CAST(b.SupplierCode AS VARCHAR(100))) AS supplier_code,
                   CAST(RTRIM(sn.suppliername) AS VARCHAR(300))  AS supplier_name
            FROM #base b
            LEFT JOIN #sale sale ON sale.ProductCode = b.ProductCode
            LEFT JOIN #old  old  ON old.ProductCode = b.ProductCode
            LEFT JOIN #roll roll ON roll.ProductCode = b.ProductCode
            LEFT JOIN #bat  bat  ON bat.ProductCode = b.ProductCode
            LEFT JOIN #pur  pur  ON pur.ProductCode = b.ProductCode
            LEFT JOIN #sup  sup  ON sup.ProductCode = b.ProductCode
            LEFT JOIN #sn sn ON sn.code = COALESCE(sup.supplier_code, CAST(b.SupplierCode AS VARCHAR(100)))
            WHERE b.stock > 0 OR ISNULL(bat.batch_stock, 0) > 0 OR ISNULL(sale.sales_180, 0) > 0;
            """,
            (tenant_id, store_id, d30, d90, d180, today, near),
        )
        while cur.description is None and cur.nextset():
            pass
        return _floatify(_rows_to_dicts(cur))
    finally:
        conn.close()


def product_batches(tenant_id, store_id, product_code):
    """Every batch of one store product that holds (or once held) stock --
    batch-wise expiry, received / last-sold dates and valuation."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT b.BatchCode                         AS batch_code,
                   RTRIM(b.BatchDescription)           AS batch,
                   b.Stock                             AS stock,
                   b.ExpiryDate                        AS expiry_date,
                   COALESCE(b.GrnDate, b.LastReceivedDate) AS received_date,
                   b.LastSaleDate                      AS last_sale_date,
                   b.GrnNumber                         AS grn_no,
                   RTRIM(b.InvoiceNumber)              AS invoice_no,
                   CAST(b.SupplierCode AS VARCHAR(100)) AS supplier_code,
                   CAST(RTRIM(s.suppliername) AS VARCHAR(300)) AS supplier_name,
                   b.PurchasePrice                     AS ptr,
                   b.ItemCost                          AS item_cost,
                   b.MRP                               AS mrp,
                   b.SaleUnit                          AS sale_unit,
                   RTRIM(b.SubLocation)                AS rack,
                   COALESCE(b.GrsStkValueatCost,
                            b.Stock * COALESCE(NULLIF(b.ItemCost, 0), b.PurchasePrice) / NULLIF(b.SaleUnit, 0)) AS cost_value,
                   b.Stock * b.MRP / NULLIF(b.SaleUnit, 0) AS mrp_value
            FROM sync.Batches b
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = b.tenant_id AND s.store_id = b.store_id
               AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(b.SupplierCode AS VARCHAR(100))
            WHERE b.tenant_id = ? AND b.store_id = ? AND b.ProductCode = TRY_CAST(? AS INT)
              AND ISNULL(b.Stock, 0) <> 0
            ORDER BY b.ExpiryDate, b.BatchCode
            """,
            (tenant_id, store_id, str(product_code)),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def monthly_movement(tenant_id, store_id, months=6):
    """Store-level monthly movement from the POS ProductTrans rollup for the
    last `months` calendar months: quantity in (purchase + transfer in), out
    (sales + transfer out), closing stock value at cost, and how many products
    had stock but no sale that month."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CONVERT(VARCHAR(7), MonthOfStatistics, 120) AS ym,
                   SUM(ISNULL(PurchaseQuantity, 0) + ISNULL(TransferInQuantity, 0)) AS qty_in,
                   SUM(ISNULL(SaleQuantity, 0) + ISNULL(TransferOutQuantity, 0))    AS qty_out,
                   SUM(CASE WHEN StockInHand > 0 THEN ISNULL(StockValueAtCostPrice, 0) ELSE 0 END) AS stock_value,
                   SUM(CASE WHEN StockInHand > 0 AND ISNULL(SaleQuantity, 0) <= 0
                             AND ISNULL(TransferOutQuantity, 0) <= 0 THEN 1 ELSE 0 END) AS idle_products,
                   SUM(CASE WHEN StockInHand > 0 THEN 1 ELSE 0 END)                 AS stocked_products
            FROM sync.ProductTrans
            WHERE tenant_id = ? AND store_id = ?
              AND MonthOfStatistics >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - ?, 0)
            GROUP BY CONVERT(VARCHAR(7), MonthOfStatistics, 120)
            ORDER BY ym
            """,
            (tenant_id, store_id, int(months) - 1),
        )
        return _floatify(_rows_to_dicts(cur))
    finally:
        conn.close()


def mapping_edges(tenant_id, store_ids, keep):
    """AUTO / APPROVED dbo.product_mapping edges among these stores, as
    (store_a, code_a, store_b, code_b, confidence) tuples, streamed and kept
    only when both ends are in `keep` (a set of (STORE_ID_UPPER, code)) -- the
    tenant table holds ~600k edges, so they are never all materialised as
    dicts. Same identity rule as Procurement's Other-stores panel
    (intelligence_repository.resolve_mapped_stores): ProductCode is never a
    cross-store key on its own; an edge is undirected."""
    if not store_ids:
        return []
    marks = ", ".join(["?"] * len(store_ids))
    out = []
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT UPPER(CAST(source_store_id AS VARCHAR(36))), CAST(source_product_code AS VARCHAR(100)),
                   UPPER(CAST(target_store_id AS VARCHAR(36))), CAST(target_product_code AS VARCHAR(100)),
                   confidence
            FROM dbo.product_mapping
            WHERE tenant_id = ? AND is_deleted = 0
              AND status IN ('AUTO', 'APPROVED')
              AND target_product_code IS NOT NULL
              AND source_store_id IN ({marks})
              AND target_store_id IN ({marks})
            """,
            (tenant_id, *store_ids, *store_ids),
        )
        while True:
            chunk = cur.fetchmany(20000)
            if not chunk:
                break
            for sa, ca, sb, cb, conf in chunk:
                if sa != sb and (sa, ca) in keep and (sb, cb) in keep:
                    out.append((sa, ca, sb, cb, float(conf) if conf is not None else None))
        return out
    finally:
        conn.close()
