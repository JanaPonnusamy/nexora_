"""Data access for the Procurement Snapshot Engine — Sprint 3.

Targets NEXORA_PLATFORM only. Reads raw operational values via the source
procedure ``procurement.usp_VplSnapshotSource`` and writes them back onto the
VPL product rows. All writes are tenant-scoped and run inside a single
transaction; full refreshes use a staged bulk UPDATE.

No procurement calculations, order quantities or supplier assignment here —
this layer only loads and persists raw snapshot values.
"""

from config.database import get_connection
from modules.procurement._dbutil import as_uid as _as_uid, rows_to_dicts as _rows_to_dicts

# Raw snapshot columns written from the source procedure result set.
SNAPSHOT_COLUMNS = (
    "current_stock_qty",
    "available_stock_qty",
    "pending_purchase_qty",
    "pending_sales_qty",
    "last_purchase_date",
    "last_purchase_qty",
    "last_purchase_rate",
    "last_sale_date",
    "last_sale_qty",
    "avg_daily_sales",
    "avg_monthly_sales",
    "expiry_qty",
    "near_expiry_qty",
    "supplier_count",
    "preferred_supplier_id",
)


# --------------------------------------------------------------------------
# source read
# --------------------------------------------------------------------------

def read_source(conn, tenant_id, vpl_id, product_id=None):
    """Return raw snapshot rows (list of dicts) for a VPL or single product.

    Uses an existing connection so the read participates in the caller's
    transaction.
    """
    cursor = conn.cursor()
    cursor.execute(
        "EXEC procurement.usp_VplSnapshotSource "
        "@TenantId=?, @VplId=?, @ProductId=?",
        (tenant_id, vpl_id, product_id),
    )
    if not cursor.description:
        return []
    return _rows_to_dicts(cursor)


# --------------------------------------------------------------------------
# write (bulk + single)  — caller owns the transaction
# --------------------------------------------------------------------------

def _set_clause():
    return ", ".join(f"{col} = stage.{col}" for col in SNAPSHOT_COLUMNS)


def bulk_write_snapshot(conn, tenant_id, vpl_id, rows):
    """Stage source rows and UPDATE-join them onto the VPL products.

    Returns the number of product rows updated. Runs on the caller's
    connection/transaction (no commit here).
    """
    if not rows:
        return 0

    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE #SnapshotStage
        (
            product_id            UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
            current_stock_qty     DECIMAL(18,3) NULL,
            available_stock_qty   DECIMAL(18,3) NULL,
            pending_purchase_qty  DECIMAL(18,3) NULL,
            pending_sales_qty     DECIMAL(18,3) NULL,
            last_purchase_date    DATE NULL,
            last_purchase_qty     DECIMAL(18,3) NULL,
            last_purchase_rate    DECIMAL(18,4) NULL,
            last_sale_date        DATE NULL,
            last_sale_qty         DECIMAL(18,3) NULL,
            avg_daily_sales       DECIMAL(18,4) NULL,
            avg_monthly_sales     DECIMAL(18,4) NULL,
            expiry_qty            DECIMAL(18,3) NULL,
            near_expiry_qty       DECIMAL(18,3) NULL,
            supplier_count        INT NULL,
            preferred_supplier_id UNIQUEIDENTIFIER NULL
        )
        """
    )

    stage_rows = [
        tuple([row["product_id"]] + [row.get(col) for col in SNAPSHOT_COLUMNS])
        for row in rows
    ]
    placeholders = ", ".join(["?"] * (len(SNAPSHOT_COLUMNS) + 1))
    cursor.fast_executemany = True
    cursor.executemany(
        f"""
        INSERT INTO #SnapshotStage
            (product_id, {", ".join(SNAPSHOT_COLUMNS)})
        VALUES ({placeholders})
        """,
        stage_rows,
    )

    cursor.execute(
        f"""
        UPDATE target
        SET {_set_clause()},
            target.snapshot_refreshed_on = GETDATE(),
            target.updated_at = GETDATE()
        FROM procurement.procurement_virtual_products target
        INNER JOIN #SnapshotStage stage
            ON stage.product_id = target.product_id
        WHERE target.tenant_id = ? AND target.refresh_id = ?
        """,
        (tenant_id, vpl_id),
    )
    updated = cursor.rowcount

    cursor.execute("DROP TABLE #SnapshotStage")
    return updated


def write_one_snapshot(conn, tenant_id, vpl_id, product_id, values):
    """Write a single product's snapshot values. Caller owns the transaction."""
    set_sql = ", ".join(f"{col} = ?" for col in SNAPSHOT_COLUMNS)
    params = [values.get(col) for col in SNAPSHOT_COLUMNS]

    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE procurement.procurement_virtual_products
        SET {set_sql},
            snapshot_refreshed_on = GETDATE(),
            updated_at = GETDATE()
        WHERE tenant_id = ? AND refresh_id = ? AND product_id = ?
        """,
        params + [tenant_id, vpl_id, product_id],
    )
    return cursor.rowcount


def stamp_header(conn, tenant_id, vpl_id, status, refreshed_by):
    """Update VPL header status + last-snapshot audit. Caller owns the txn."""
    refreshed_by = _as_uid(refreshed_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_refreshes
        SET snapshot_status = ?,
            last_snapshot_on = GETDATE(),
            last_snapshot_by = ?,
            updated_by = ?,
            updated_at = GETDATE()
        WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (status, refreshed_by, refreshed_by, vpl_id, tenant_id),
    )
    return cursor.rowcount


def set_status_only(conn, tenant_id, vpl_id, status):
    """Transition status without touching last-snapshot audit (e.g. Refreshing)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_refreshes
        SET snapshot_status = ?, updated_at = GETDATE()
        WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (status, vpl_id, tenant_id),
    )
    return cursor.rowcount


# --------------------------------------------------------------------------
# product selection helpers (own connection — read only)
# --------------------------------------------------------------------------

def list_product_ids(tenant_id, vpl_id, changed_only=False):
    """Product ids in a VPL. changed_only -> never snapshotted, or modified
    after the last snapshot."""
    where = "tenant_id = ? AND refresh_id = ?"
    params = [tenant_id, vpl_id]
    if changed_only:
        where += (
            " AND (snapshot_refreshed_on IS NULL"
            " OR updated_at > snapshot_refreshed_on)"
        )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT product_id
            FROM procurement.procurement_virtual_products
            WHERE {where}
            """,
            params,
        )
        return [str(r[0]) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_progress(tenant_id, vpl_id):
    """Return snapshot progress counts + VPL status for a VPL."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_products,
                SUM(CASE WHEN snapshot_refreshed_on IS NOT NULL
                         THEN 1 ELSE 0 END) AS refreshed_products,
                SUM(CASE WHEN snapshot_refreshed_on IS NULL
                         OR updated_at > snapshot_refreshed_on
                         THEN 1 ELSE 0 END) AS pending_products
            FROM procurement.procurement_virtual_products
            WHERE tenant_id = ? AND refresh_id = ?
            """,
            (tenant_id, vpl_id),
        )
        row = cursor.fetchone()
        return {
            "total_products": row[0] or 0,
            "refreshed_products": row[1] or 0,
            "pending_products": row[2] or 0,
        }
    finally:
        conn.close()
