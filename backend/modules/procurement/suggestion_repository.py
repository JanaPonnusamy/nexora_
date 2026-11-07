"""Reads for the product Suggestion panel: suppliers for one store product and
the other stores' stock of the same product. Keyed by store + product code
(not a procurement order item), so it answers for ANY product -- on a
refresh, on the legacy order, or on neither. Read-only.
"""

from datetime import date, timedelta

from config.database import get_connection
from modules.procurement._dbutil import (
    rows_to_dicts as _rows_to_dicts,
    store_stock_expr as _store_stock_expr,
    stringify as _stringify,
)


def purchase_suppliers(tenant_id, store_id, product_code):
    """Every supplier this store bought the product from: purchase count, and
    the LAST purchase's date / GRN / PTR / cost / MRP / qty / free.

    Internal transfers (InvoiceSeries 'TI') are not supplier purchases -- their
    SupplierCode collides with real supplier codes -- so they are left out.
    Products a supplier was excluded from for the next cycle (supplier reply
    "not available") are left out too, same as the Purchase Manager queue.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT OBJECT_ID('procurement.supplier_product_exclusions')")
        has_exclusions = cursor.fetchone()[0] is not None
        exclusion = (
            """
              AND NOT EXISTS (
                  SELECT 1 FROM procurement.supplier_product_exclusions ex
                  WHERE ex.tenant_id = pt.tenant_id AND ex.store_id = pt.store_id
                    AND ex.supplier_code = CAST(pt.SupplierCode AS VARCHAR(100))
                    AND ex.product_code = CAST(pt.ProductCode AS VARCHAR(100))
              )
            """
            if has_exclusions else ""
        )
        cursor.execute(
            f"""
            WITH pt AS (
                SELECT CAST(pt.SupplierCode AS VARCHAR(100)) AS supplier_code,
                       pt.grndate, pt.Grnnumber, pt.purchaseprice, pt.itemcost, pt.mrp,
                       pt.stockreceived, pt.FreeQty, pt.ProductDiscPercent,
                       COUNT(*) OVER (PARTITION BY pt.SupplierCode) AS purchase_frequency,
                       ROW_NUMBER() OVER (PARTITION BY pt.SupplierCode ORDER BY pt.grndate DESC, pt.ID DESC) AS rn
                FROM sync.PurchaseTrans pt
                WHERE pt.tenant_id = ? AND pt.store_id = ? AND pt.ProductCode = TRY_CAST(? AS INT)
                  AND pt.SupplierCode IS NOT NULL
                  AND ISNULL(pt.InvoiceSeries, '') <> 'TI'
                  {exclusion}
            )
            SELECT pt.supplier_code,
                   CAST(RTRIM(s.suppliername) AS VARCHAR(300)) AS supplier_name,
                   pt.purchase_frequency,
                   pt.grndate                         AS last_grn_date,
                   CAST(pt.Grnnumber AS VARCHAR(100)) AS last_grn_no,
                   pt.purchaseprice                   AS last_purchase_rate,
                   pt.itemcost                        AS last_item_cost,
                   pt.mrp                             AS last_mrp,
                   pt.stockreceived                   AS last_qty,
                   pt.FreeQty                         AS last_free,
                   pt.ProductDiscPercent              AS last_discount,
                   ISNULL(s.auto_assign, 1)           AS auto_assign
            FROM pt
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ? AND s.store_id = ?
               AND CAST(s.suppliercode AS VARCHAR(100)) = pt.supplier_code
            WHERE pt.rn = 1
            """,
            (tenant_id, store_id, str(product_code), tenant_id, store_id),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def live_supplier_stock(tenant_id, store_id, product_code):
    """Suppliers whose imported live stock list (procurement.supplier_stock)
    carries this store product with stock > 0."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT OBJECT_ID('procurement.supplier_stock')")
        if cursor.fetchone()[0] is None:
            return []
        cursor.execute(
            """
            SELECT CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                   CAST(RTRIM(s.suppliername) AS VARCHAR(300)) AS supplier_name,
                   ss.available_stock, ss.ptr, ss.mrp, ss.discount, ss.free, ss.scheme,
                   ss.transaction_date
            FROM procurement.supplier_stock ss
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ss.tenant_id AND s.store_id = ss.store_id
               AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(ss.supplier_code AS VARCHAR(100))
            WHERE ss.tenant_id = ? AND ss.store_id = ?
              AND CAST(ss.product_code AS VARCHAR(100)) = ?
              AND ss.is_active = 1 AND ISNULL(ss.available_stock, 0) > 0
            """,
            (tenant_id, store_id, str(product_code)),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def store_product_facts(tenant_id, pairs, window_days):
    """Stock and movement of specific (store_id, product_code) pairs: current
    stock, sales in the window, last sale and last purchase date. Sales are
    every valid sale series (a warehouse 'sells' by despatch), as in the
    network movement metrics."""
    if not pairs:
        return []
    cutoff = date.today() - timedelta(days=int(window_days))
    values = ", ".join(["(?, ?)"] * len(pairs))
    params = [x for pair in pairs for x in (pair[0], str(pair[1]))]
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            WITH pairs(store_id, code) AS (
                SELECT CAST(v.store_id AS UNIQUEIDENTIFIER), TRY_CAST(v.code AS INT)
                FROM (VALUES {values}) v(store_id, code)
            )
            SELECT CAST(p.store_id AS VARCHAR(36))       AS store_id,
                   CAST(p.ProductCode AS VARCHAR(100))   AS product_code,
                   p.ProductName                         AS product_name,
                   CAST({_store_stock_expr("p")} AS DECIMAL(18,3)) AS stock,
                   p.MRP                                 AS mrp,
                   (SELECT MAX(psi.TransactionDate) FROM sync.ProductSaleInformation psi
                     WHERE psi.tenant_id = p.tenant_id AND psi.store_id = p.store_id
                       AND psi.ProductCode = p.ProductCode AND ISNULL(psi.TransactionValidity, 0) = 0
                   ) AS last_sale_date,
                   (SELECT SUM(psi.Quantity) FROM sync.ProductSaleInformation psi
                     WHERE psi.tenant_id = p.tenant_id AND psi.store_id = p.store_id
                       AND psi.ProductCode = p.ProductCode AND ISNULL(psi.TransactionValidity, 0) = 0
                       AND psi.TransactionDate >= ?
                   ) AS window_sales_qty,
                   (SELECT MAX(pt.grndate) FROM sync.PurchaseTrans pt
                     WHERE pt.tenant_id = p.tenant_id AND pt.store_id = p.store_id
                       AND pt.ProductCode = p.ProductCode
                   ) AS last_purchase_date
            FROM pairs
            INNER JOIN sync.Products p
                ON p.tenant_id = ? AND p.store_id = pairs.store_id AND p.ProductCode = pairs.code
            """,
            (*params, cutoff, tenant_id),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def store_monthly_movement(tenant_id, pairs, months):
    """Monthly ProductTrans rollup (the POS's own) of specific (store_id,
    product_code) pairs for the last `months` calendar months, current month
    included. IN = purchase + transfer in, OUT = sales + transfer out (a
    warehouse moves stock out by transfer/despatch), STOCK = closing stock."""
    if not pairs:
        return []
    values = ", ".join(["(?, ?)"] * len(pairs))
    params = [x for pair in pairs for x in (pair[0], str(pair[1]))]
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            WITH pairs(store_id, code) AS (
                SELECT CAST(v.store_id AS UNIQUEIDENTIFIER), TRY_CAST(v.code AS INT)
                FROM (VALUES {values}) v(store_id, code)
            )
            SELECT CAST(pt.store_id AS VARCHAR(36))                 AS store_id,
                   CAST(pt.ProductCode AS VARCHAR(100))             AS product_code,
                   CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120)   AS ym,
                   ISNULL(pt.PurchaseQuantity, 0) + ISNULL(pt.TransferInQuantity, 0) AS qty_in,
                   ISNULL(pt.SaleQuantity, 0) + ISNULL(pt.TransferOutQuantity, 0)    AS qty_out,
                   ISNULL(pt.StockInHand, 0)                        AS stock
            FROM pairs
            INNER JOIN sync.ProductTrans pt
                ON pt.tenant_id = ? AND pt.store_id = pairs.store_id AND pt.ProductCode = pairs.code
            WHERE pt.MonthOfStatistics >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - ?, 0)
            ORDER BY pt.MonthOfStatistics
            """,
            (*params, tenant_id, int(months) - 1),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()
