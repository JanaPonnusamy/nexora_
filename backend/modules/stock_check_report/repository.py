"""Read-only data access for the Stock Check Report module.

Ported from the legacy VB6 OrderRpt "Stock Check" report (D:/OrderRpt/
ReportsExport.frm, Command9_Click / Command11_Click): a physical-count sheet
of every batch in a sublocation range. The legacy app queried the store's
live BATCHES/PRODUCTS tables directly; this reads the already-synced
`sync.Batches` / `sync.Products` tables in NEXORA_PLATFORM instead, so the
caller triggers a sync first (see sync.runtime_service) and reports off that.
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


def get_stock_check_rows(tenant_id, store_id, sublocation_from, sublocation_to):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
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
            WHERE b.tenant_id = ?
              AND b.store_id  = ?
              AND ISNULL(b.Stock, 0) > 0
              AND p.SubLocation IS NOT NULL
              AND LTRIM(RTRIM(p.SubLocation)) <> ''
              AND LTRIM(RTRIM(p.SubLocation)) BETWEEN ? AND ?
            ORDER BY p.SubLocation, p.ProductName, b.ExpiryDate
            """,
            (tenant_id, store_id, tenant_id, store_id, sublocation_from, sublocation_to),
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
