"""Reads for the Supplier Rate Engine.

Two independent purchase-data sources, each on its own SQL Server instance:

  SMS tenant   dbo.PurchaseTrans on OrderSMS (192.168.10.32) -- one shared
               table for SMA/SMF/SMG/SHP, store identified by StoreName.
               No product-name column: join dbo.Products (also StoreName-
               scoped) for it. Bill key = InvoiceSeries + Grnnumber.
  Nathan tenant sync.PurchaseTrans on NEXORA_PLATFORM (192.168.10.73) --
               store_id is a GUID, joined to dbo.stores for store_code.
               Product name via sync.Products on (tenant_id, ProductCode).

Verified live 2026-11-19 against both servers. ProductCode is tenant-local
and NOT comparable across tenants -- product-name matching (normalised:
upper-cased, non-alphanumerics stripped) is the only cross-tenant key.

InvoiceSeries = 'TI' is an internal stock transfer, not a real purchase (see
memory ti-transfer-supplier-collision) and is always excluded here.
"""

import re

from modules.supplier_rate_engine.database import get_connection

NATHAN_TENANT_ID = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"
SMS_STORES = ("SMA", "SMF", "SMG", "SHP")
NMW_STORE = "NMW"
STORE_TENANTS = {
    "SMS": {"stores": ("SMA", "SMF", "SMG", "SHP"), "batch_wise": False},
    "SUCCESS": {"stores": ("SMA", "SMAG", "SMBS", "SMGH", "SMKP"), "batch_wise": True},
}


def normalize_name(name):
    return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def _rows_to_dicts(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def sms_purchase_lines(period_start, period_end, stores=SMS_STORES):
    """SMS tenant purchase lines (dbo.PurchaseTrans), real purchases only
    (InvoiceSeries <> 'TI'), with product name, for the given date range."""
    marks = ", ".join(["?"] * len(stores))
    conn = get_connection("SMS")
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT pt.StoreName                                   AS store,
                   pt.ProductCode                                 AS product_code,
                   p.ProductName                                  AS product_name,
                   pt.InvoiceSeries                                AS invoice_series,
                   pt.Grnnumber                                    AS grn_number,
                   pt.grndate                                      AS grn_date,
                   pt.stockreceived                                AS qty,
                   ISNULL(pt.FreeQty, 0)                           AS free_qty,
                   pt.itemcost                                     AS item_cost,
                   pt.purchaseprice                                AS purchase_price,
                   pt.suppliername                                 AS supplier_name,
                   pt.suppliercode                                 AS supplier_code
            FROM dbo.PurchaseTrans pt
            LEFT JOIN dbo.Products p
                ON p.StoreName = pt.StoreName AND p.ProductCode = pt.ProductCode
            WHERE pt.StoreName IN ({marks})
              AND ISNULL(pt.InvoiceSeries, '') <> 'TI'
              AND pt.grndate >= ? AND pt.grndate < ?
            """,
            (*stores, period_start, period_end),
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def nathan_purchase_lines(period_start, period_end, tenant_id=NATHAN_TENANT_ID, store=None):
    """Nathan tenant purchase lines (sync.PurchaseTrans on NEXORA_PLATFORM),
    real purchases only, with store code, product name, MRP and sale unit.
    `store`, if given (e.g. NMW_STORE), restricts to that one Nathan store --
    this report's baseline is NMW specifically, not the whole chain."""
    conn = get_connection("NATHAN")
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT s.store_code                                    AS store,
                   pt.ProductCode                                  AS product_code,
                   pr.ProductName                                  AS product_name,
                   pt.Grnnumber                                    AS grn_number,
                   pt.grndate                                      AS grn_date,
                   pt.stockreceived                                AS qty,
                   ISNULL(pt.FreeQty, 0)                           AS free_qty,
                   pt.itemcost                                     AS item_cost,
                   pt.purchaseprice                                AS purchase_price,
                   pt.mrp                                          AS mrp,
                   pt.SaleUnit                                     AS sale_unit,
                   pr.PurchaseUnit                                 AS purchase_unit,
                   pt.SupplierCode                                 AS supplier_code,
                   RTRIM(COALESCE(sup.suppliername,
                         CAST(pt.SupplierCode AS VARCHAR(100))))   AS supplier_name
            FROM sync.PurchaseTrans pt
            INNER JOIN dbo.stores s ON s.store_id = pt.store_id
            LEFT JOIN sync.Products pr
                ON pr.tenant_id = pt.tenant_id AND pr.store_id = pt.store_id AND pr.ProductCode = pt.ProductCode
            LEFT JOIN sync.Suppliers sup
                ON sup.tenant_id = pt.tenant_id
               AND CAST(sup.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
            WHERE pt.tenant_id = ?
              AND ISNULL(pt.InvoiceSeries, '') <> 'TI'
              AND pt.grndate >= ? AND pt.grndate < ?
              {"AND s.store_code = ?" if store else ""}
            """,
            (tenant_id, period_start, period_end, *([store] if store else [])),
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def store_tenant_purchase_lines(tenant_key, period_start, period_end):
    """Generic reader for the SMS-family tenants (SMS, Success): both share
    the same dbo.PurchaseTrans/dbo.Products shape, store-scoped, on
    192.168.10.32 (different database per tenant). Returns MRP, sale unit
    and batch code per line -- Success is compared batch-wise, SMS bill-wise,
    but both need BatchCode available for that."""
    conf = STORE_TENANTS.get(tenant_key.upper())
    if not conf:
        raise ValueError(f"Unknown store-tenant '{tenant_key}' (expected one of {list(STORE_TENANTS)})")
    stores = conf["stores"]
    marks = ", ".join(["?"] * len(stores))
    conn = get_connection(tenant_key.upper())
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT pt.StoreName                                   AS store,
                   pt.ProductCode                                 AS product_code,
                   p.ProductName                                  AS product_name,
                   pt.InvoiceSeries                                AS invoice_series,
                   pt.Grnnumber                                    AS grn_number,
                   pt.grndate                                      AS grn_date,
                   pt.BatchCode                                    AS batch_code,
                   pt.stockreceived                                AS qty,
                   ISNULL(pt.FreeQty, 0)                           AS free_qty,
                   pt.itemcost                                     AS item_cost,
                   pt.purchaseprice                                AS purchase_price,
                   pt.mrp                                          AS mrp,
                   pt.SaleUnit                                     AS sale_unit,
                   p.PurchaseUnit                                  AS purchase_unit,
                   pt.suppliername                                 AS supplier_name,
                   pt.suppliercode                                 AS supplier_code
            FROM dbo.PurchaseTrans pt
            LEFT JOIN dbo.Products p
                ON p.StoreName = pt.StoreName AND p.ProductCode = pt.ProductCode
            WHERE pt.StoreName IN ({marks})
              AND ISNULL(pt.InvoiceSeries, '') <> 'TI'
              AND pt.grndate >= ? AND pt.grndate < ?
            """,
            (*stores, period_start, period_end),
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def nmw_batch_activity(period_start, period_end):
    """Every NMW purchase line (batch-wise) in [period_start, period_end) --
    cost, PTR, MRP, unit, supplier -- for ANY product with a real purchase in
    that window, regardless of current stock level (a product can be fully
    sold out / stock=0 today and still belong in this 90-day activity report,
    since it reflects transactions, not a current-stock snapshot)."""
    conn = get_connection("NATHAN")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pr.ProductName                                  AS product_name,
                   pt.ProductCode                                  AS product_code,
                   pt.BatchCode                                    AS batch_code,
                   pt.Grnnumber                                    AS grn_number,
                   pt.grndate                                      AS grn_date,
                   pt.stockreceived                                AS qty,
                   ISNULL(pt.FreeQty, 0)                           AS free_qty,
                   pt.itemcost                                     AS item_cost,
                   pt.purchaseprice                                AS purchase_price,
                   pt.mrp                                          AS mrp,
                   pt.SaleUnit                                     AS sale_unit,
                   pr.PurchaseUnit                                 AS purchase_unit,
                   RTRIM(COALESCE(sup.suppliername,
                         CAST(pt.SupplierCode AS VARCHAR(100))))   AS supplier_name
            FROM sync.PurchaseTrans pt
            INNER JOIN dbo.stores s ON s.store_id = pt.store_id
            LEFT JOIN sync.Products pr
                ON pr.tenant_id = pt.tenant_id AND pr.store_id = pt.store_id AND pr.ProductCode = pt.ProductCode
            LEFT JOIN sync.Suppliers sup
                ON sup.tenant_id = pt.tenant_id
               AND CAST(sup.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
            WHERE pt.tenant_id = ?
              AND s.store_code = ?
              AND ISNULL(pt.InvoiceSeries, '') <> 'TI'
              AND pt.grndate >= ? AND pt.grndate < ?
            ORDER BY pr.ProductName, pt.grndate
            """,
            (NATHAN_TENANT_ID, NMW_STORE, period_start, period_end),
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def nmw_product_name_suggest(name_fragment, store=NMW_STORE, limit=20):
    """Distinct NMW product names containing `name_fragment` -- fast, catalog
    -only (sync.Products, no PurchaseTrans join), for a live typeahead
    dropdown. Case-insensitive, whitespace-tolerant, same rules as
    nathan_variant_search's candidate-code step."""
    conn = get_connection("NATHAN")
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT DISTINCT TOP {int(limit)} RTRIM(pr.ProductName) AS product_name
            FROM sync.Products pr
            INNER JOIN dbo.stores s ON s.store_id = pr.store_id
            WHERE pr.tenant_id = ? AND s.store_code = ?
              AND REPLACE(pr.ProductName, '  ', ' ') COLLATE Latin1_General_CI_AS
                  LIKE '%' + REPLACE(?, '  ', ' ') + '%' COLLATE Latin1_General_CI_AS
            ORDER BY RTRIM(pr.ProductName)
            """,
            (NATHAN_TENANT_ID, store, name_fragment),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def nathan_variant_search(name_fragment, period_start, period_end, store=NMW_STORE):
    """Find every distinct stored product-name string at NMW containing
    `name_fragment` (case-insensitive substring, no fuzzy scoring), with the
    MRP/unit combinations found for each -- the "variant picker" data. Exact
    string matching only; it is on the CALLER (the UI's review step) to
    decide which returned variant(s) actually belong to the product the
    reference file meant, per the NAN PRO false-match lesson this session.

    Two-step to stay fast: a leading-wildcard LIKE can't use an index, so it
    must not run directly against sync.PurchaseTrans (millions of rows,
    .73's 1GB buffer-pool cap makes that scan stall -- see memory
    sql-server-express-buffer-pool-cap). Instead, find candidate ProductCodes
    from sync.Products (orders of magnitude smaller) first, then join those
    specific codes into PurchaseTrans for the date range."""
    conn = get_connection("NATHAN")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pr.ProductCode
            FROM sync.Products pr
            INNER JOIN dbo.stores s ON s.store_id = pr.store_id
            WHERE pr.tenant_id = ? AND s.store_code = ?
              AND REPLACE(pr.ProductName, '  ', ' ') COLLATE Latin1_General_CI_AS
                  LIKE '%' + REPLACE(?, '  ', ' ') + '%' COLLATE Latin1_General_CI_AS
            """,
            (NATHAN_TENANT_ID, store, name_fragment),
        )
        codes = [r[0] for r in cur.fetchall()]
        if not codes:
            return []

        marks = ", ".join(["?"] * len(codes))
        cur.execute(
            f"""
            SELECT pr.ProductName                                  AS product_name,
                   pt.mrp                                          AS mrp,
                   pt.SaleUnit                                     AS sale_unit,
                   pr.PurchaseUnit                                 AS purchase_unit,
                   COUNT(*)                                        AS line_count,
                   MIN(pt.itemcost)                                AS min_cost,
                   MAX(pt.itemcost)                                AS max_cost
            FROM sync.PurchaseTrans pt
            INNER JOIN dbo.stores s ON s.store_id = pt.store_id
            LEFT JOIN sync.Products pr
                ON pr.tenant_id = pt.tenant_id AND pr.store_id = pt.store_id AND pr.ProductCode = pt.ProductCode
            WHERE pt.tenant_id = ?
              AND s.store_code = ?
              AND ISNULL(pt.InvoiceSeries, '') <> 'TI'
              AND pt.grndate >= ? AND pt.grndate < ?
              AND pt.ProductCode IN ({marks})
            GROUP BY pr.ProductName, pt.mrp, pt.SaleUnit, pr.PurchaseUnit
            ORDER BY pr.ProductName, pt.mrp
            """,
            (NATHAN_TENANT_ID, store, period_start, period_end, *codes),
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()
