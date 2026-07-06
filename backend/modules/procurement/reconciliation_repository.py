"""Data access for GRN completion + assignment reconciliation (Sprint 3).

SQL only for reads/writes; the reconciliation rules live in
reconciliation_rules.py. Purchase receipts come from the store-operational
PurchaseTrans, which reaches the platform via sync — the marked block is the
SINGLE integration point (empty until wired). Writes run on a caller-owned
transaction.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def get_refresh(tenant_id, refresh_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT refresh_id, cycle_id, store_id, snapshot_status,
                   last_grn_number, grn_completed_at
            FROM procurement.procurement_refreshes
            WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (refresh_id, tenant_id),
        )
        rows = _rows_to_dicts(cursor)
        return rows[0] if rows else None
    finally:
        conn.close()


def store_last_grn(conn, tenant_id, refresh_id, last_grn):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_refreshes
        SET last_grn_number = ?, grn_completed_at = GETDATE(), updated_at = GETDATE()
        WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
        """,
        (last_grn, refresh_id, tenant_id),
    )
    return cursor.rowcount


def read_purchase_receipts(conn, tenant_id, store_id, last_grn):
    """Synced supplier receipts (PurchaseTrans) up to the Last GRN Number.

    Returns product_code / supplier_code / received_qty / grn_no /
    supplier_bill_no. INTEGRATION POINT — wire the real PurchaseTrans read here;
    empty until then, so reconciliation is a safe no-op.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        /* Real synced receipts, attributed by SupplierCode (canonical supplier
           reference in sync.PurchaseTrans). Grouped by product + supplier so
           multi-supplier order items reconcile per assignment. */
        SELECT
            CAST(pt.ProductCode AS VARCHAR(100))            AS product_code,
            CAST(pt.SupplierCode AS VARCHAR(100))           AS supplier_code,
            CAST(SUM(ISNULL(pt.StockReceived, 0)) AS DECIMAL(18,3)) AS received_qty,
            CAST(MAX(pt.GRNNumber) AS VARCHAR(100))         AS grn_no,
            CAST(MAX(pt.InvoiceSeries) AS VARCHAR(100))     AS supplier_bill_no
        FROM sync.PurchaseTrans pt
        WHERE pt.tenant_id = ? AND pt.store_id = ?
        GROUP BY pt.ProductCode, pt.SupplierCode
        """,
        (tenant_id, store_id),
    )
    return _rows_to_dicts(cursor)


def exported_assignments(conn, tenant_id, refresh_id):
    """Live assignments awaiting receipt for the Refresh."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT assignment_id, order_item_id, product_code, supplier_code,
               assigned_qty
        FROM procurement.procurement_order_item_assignments
        WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
          AND assignment_status IN ('exported', 'partial_received')
        """,
        (tenant_id, refresh_id),
    )
    return _rows_to_dicts(cursor)


def apply_receipt(conn, tenant_id, assignment_id, received, remaining, status,
                  grn_no, bill_no):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET received_qty = ?, remaining_qty = ?, assignment_status = ?,
            grn_no = COALESCE(?, grn_no),
            supplier_bill_no = COALESCE(?, supplier_bill_no),
            last_grn_sync_at = GETDATE(), updated_at = GETDATE()
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (received, remaining, status, grn_no, bill_no, tenant_id, assignment_id),
    )
    return cursor.rowcount


def order_items_for_refresh(conn, tenant_id, refresh_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT order_item_id, final_qty
        FROM procurement.procurement_order_items
        WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
        """,
        (tenant_id, refresh_id),
    )
    return _rows_to_dicts(cursor)


def set_item_receipts(conn, tenant_id, order_item_id, received, remaining, status):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_items
        SET received_qty = ?, remaining_qty = ?, item_status = ?,
            updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (received, remaining, status, tenant_id, order_item_id),
    )
    return cursor.rowcount


def item_received_total(conn, tenant_id, order_item_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COALESCE(SUM(received_qty), 0)
        FROM procurement.procurement_order_item_assignments
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (tenant_id, order_item_id),
    )
    return cursor.fetchone()[0] or 0
