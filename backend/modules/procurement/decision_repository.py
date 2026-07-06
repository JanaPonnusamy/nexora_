"""Data access for the Procurement Decision Engine.

SQL here is used ONLY to read source data, bulk-write the generated VPL, and
finalize the Refresh/Cycle — never for business rules (those live in
decision_rules.py). Writes run on a caller-owned connection/transaction so the
whole generation is atomic. No row-by-row inserts: the VPL is written with a
single fast_executemany bulk insert.
"""

from datetime import date, timedelta
from decimal import Decimal

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def _floatify(rows):
    """pyodbc returns DECIMAL as decimal.Decimal; the pure rule engine does
    float arithmetic. Coerce numeric source values to float at this boundary."""
    for row in rows:
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = float(value)
    return rows


# --------------------------------------------------------------------------
# Refresh header (own connection — read only)
# --------------------------------------------------------------------------

def get_refresh_for_generation(tenant_id, refresh_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT refresh_id, cycle_id, store_id,
                   rolling_days, min_days, max_days, snapshot_status
            FROM procurement.procurement_refreshes
            WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (refresh_id, tenant_id),
        )
        rows = _rows_to_dicts(cursor)
        return rows[0] if rows else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Source dataset (Stage 1)  — one bulk read, no N+1
# --------------------------------------------------------------------------

def load_source(conn, tenant_id, store_id, params):
    """Return the per-product RAW source rows for the decision run.

    Reads REAL synchronized platform data from NEXORA_PLATFORM.sync.* (the same
    tables the Stock Availability module uses), for one store:

      * product master + current stock : sync.Products (ProductCode, ProductName,
        UnitDescription, TotalStock, isActive)
      * rolling-window sales metrics    : sync.ProductSaleInformation, valid rows
        (TransactionValidity = 0) within the Refresh's Rolling Days window —
        WindowSalesQty (SUM), MaxDaySaleQty (MAX daily), MaxBillQty (MAX per
        bill), BillingFrequency (distinct bills). PR-BR-001/012 aggregation.

    Effective-Available pending components (receivable / in-transit / reserved)
    have no synced source yet (Topic 05); they default to 0, so Effective
    Available = current stock for a fresh cycle. ProductCode is the store's
    integer code; product_code carries it and product_id is a per-snapshot GUID.
    DontConsiderInOrder is not part of the sync registry, so eligibility uses
    TransactionValidity only (faithful to the platform's synced schema).
    """
    if not store_id:
        return []
    rolling_days = params.rolling_days or 90
    cutoff = date.today() - timedelta(days=rolling_days)

    cursor = conn.cursor()
    cursor.execute(
        """
        WITH sales AS (
            SELECT psi.ProductCode,
                   CAST(psi.TransactionDate AS DATE) AS d,
                   CAST(psi.SeriesName AS VARCHAR(10)) + '|'
                     + CAST(psi.BillNumber AS VARCHAR(50)) + '|'
                     + CONVERT(VARCHAR(8), psi.TransactionDate, 112) AS bill_key,
                   ISNULL(psi.Quantity, 0) AS qty
            FROM sync.ProductSaleInformation psi
            WHERE psi.tenant_id = ? AND psi.store_id = ?
              AND ISNULL(psi.TransactionValidity, 0) = 0
              AND psi.TransactionDate >= ?
        ),
        per_day  AS (SELECT ProductCode, d, SUM(qty) AS q FROM sales GROUP BY ProductCode, d),
        per_bill AS (SELECT ProductCode, bill_key, SUM(qty) AS q FROM sales GROUP BY ProductCode, bill_key),
        agg AS (
            SELECT ProductCode,
                   SUM(qty) AS window_sales_qty,
                   COUNT(DISTINCT bill_key) AS billing_frequency
            FROM sales GROUP BY ProductCode
        ),
        md AS (SELECT ProductCode, MAX(q) AS max_day_sale_qty FROM per_day GROUP BY ProductCode),
        mb AS (SELECT ProductCode, MAX(q) AS max_bill_qty FROM per_bill GROUP BY ProductCode)
        SELECT
            NEWID()                              AS product_id,
            CAST(p.ProductCode AS VARCHAR(100))  AS product_code,
            p.ProductName                        AS product_name,
            CAST(NULL AS UNIQUEIDENTIFIER)       AS manufacturer_id,
            CAST(NULL AS UNIQUEIDENTIFIER)       AS category_id,
            CAST(NULL AS VARCHAR(50))            AS schedule_type,
            p.UnitDescription                    AS unit,
            CAST(ISNULL(p.isActive, 1) AS BIT)   AS is_active,
            CAST(0 AS BIT)                       AS dont_consider,
            CAST(ISNULL(agg.window_sales_qty, 0) AS DECIMAL(18,3)) AS window_sales_qty,
            CAST(ISNULL(md.max_day_sale_qty, 0)  AS DECIMAL(18,3)) AS max_day_sale_qty,
            CAST(ISNULL(mb.max_bill_qty, 0)      AS DECIMAL(18,3)) AS max_bill_qty,
            CAST(ISNULL(agg.billing_frequency, 0) AS INT)          AS billing_frequency,
            CAST(ISNULL(p.TotalStock, 0)         AS DECIMAL(18,3)) AS current_stock
        FROM sync.Products p
        LEFT JOIN agg ON agg.ProductCode = p.ProductCode
        LEFT JOIN md  ON md.ProductCode  = p.ProductCode
        LEFT JOIN mb  ON mb.ProductCode  = p.ProductCode
        WHERE p.tenant_id = ? AND p.store_id = ?
          AND ISNULL(p.isActive, 1) = 1
        """,
        (tenant_id, store_id, cutoff, tenant_id, store_id),
    )
    if not cursor.description:
        return []
    return _floatify(_rows_to_dicts(cursor))


# --------------------------------------------------------------------------
# Generation lifecycle writes  — caller owns the transaction
# --------------------------------------------------------------------------

def mark_generating(conn, tenant_id, refresh_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_refreshes
        SET snapshot_status = 'Refreshing',
            generation_started_at = GETDATE(),
            updated_at = GETDATE()
        WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (refresh_id, tenant_id),
    )
    return cursor.rowcount


def clear_products(conn, tenant_id, refresh_id):
    """Remove any prior VPL rows so re-generation is deterministic."""
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM procurement.procurement_virtual_products
        WHERE refresh_id = ? AND tenant_id = ?
        """,
        (refresh_id, tenant_id),
    )
    return cursor.rowcount


# Column order for the bulk VPL insert. Each row dict must supply every key.
INSERT_COLUMNS = (
    "tenant_id", "cycle_id", "refresh_id", "product_id",
    "product_code", "product_name", "manufacturer_id", "category_id",
    "schedule_type", "unit", "is_active", "snapshot_version",
    "avg_daily_sales", "window_sales_qty", "max_day_sale_qty", "max_bill_qty",
    "billing_frequency", "current_stock_qty", "available_stock_qty",
    "pending_purchase_qty", "pending_sales_qty",
    "days_cover", "movement_class", "stock_status",
    "effective_available_qty", "pending_used_qty",
    "target_days", "target_stock_qty", "raw_required_qty", "required_qty",
    "suggested_qty", "final_required_qty",
    "procurement_action", "trigger_reason", "reason_code", "reason_text",
)


def bulk_insert_products(conn, rows):
    """Single bulk insert of the generated VPL. Returns the rows written."""
    if not rows:
        return 0
    placeholders = ", ".join(["?"] * len(INSERT_COLUMNS))
    sql = (
        "INSERT INTO procurement.procurement_virtual_products ("
        + ", ".join(INSERT_COLUMNS)
        + ") VALUES (" + placeholders + ")"
    )
    params = [tuple(row[col] for col in INSERT_COLUMNS) for row in rows]
    cursor = conn.cursor()
    cursor.fast_executemany = True
    cursor.executemany(sql, params)
    return len(params)


def finalize(conn, tenant_id, refresh_id, cycle_id, generated_count):
    """Stage 6: publish the Refresh and point the Cycle at it."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_refreshes
        SET snapshot_status = 'Ready',
            generated_product_count = ?,
            generation_completed_at = GETDATE(),
            updated_at = GETDATE()
        WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (generated_count, refresh_id, tenant_id),
    )
    cursor.execute(
        """
        UPDATE procurement.procurement_cycles
        SET active_refresh_id = ?, updated_at = GETDATE()
        WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (refresh_id, cycle_id, tenant_id),
    )
