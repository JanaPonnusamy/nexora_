"""Data access for the Expiry Report — read-only over the synced Shopaid
supplier-expiry tables in NEXORA_PLATFORM.

Drill-down hierarchy:
  tenant -> store summary -> supplier summary -> ( pending details |
            ack-wise -> ack product details )

Given / Received / Reject come from sync.SupplierAckHeader (the supplier
acknowledgement flow: Quantity given, AcceptedQty received, RejectedQty
rejected). Pending is the still-outstanding "given but not yet claimed" items
in sync.SupplierPendingProducts (the legacy "Supplier Pending Issue Report").

Every query is scoped by tenant_id (+ store_id where applicable).
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


# ---------------------------------------------------------------------------
# Level 1 — Store-wise summary (all stores of a tenant, totals only).
# ---------------------------------------------------------------------------

def store_summary(tenant_id):
    sql = """
        SELECT
            st.store_name  AS StoreName,
            st.store_code  AS StoreCode,
            CAST(st.store_id AS VARCHAR(36)) AS StoreId,
            ISNULL(a.GivenQty, 0)      AS GivenQty,
            ISNULL(a.ReceivedQty, 0)   AS ReceivedQty,
            ISNULL(a.RejectQty, 0)     AS RejectQty,
            ISNULL(p.PendingQty, 0)    AS PendingQty,
            ISNULL(a.GivenValue, 0)    AS GivenValue,
            ISNULL(a.ReceivedValue, 0) AS ReceivedValue,
            ISNULL(p.PendingValue, 0)  AS PendingValue
        FROM dbo.stores st
        LEFT JOIN (
            SELECT store_id,
                   SUM(Quantity)                AS GivenQty,
                   SUM(AcceptedQty)             AS ReceivedQty,
                   SUM(ISNULL(RejectedQty, 0))  AS RejectQty,
                   SUM(TotalAmount)             AS GivenValue,
                   SUM(AdjustedValue)           AS ReceivedValue
            FROM sync.SupplierAckHeader
            WHERE tenant_id = ?
            GROUP BY store_id
        ) a ON a.store_id = st.store_id
        LEFT JOIN (
            SELECT store_id,
                   SUM(Quantity)    AS PendingQty,
                   SUM(TotalAmount) AS PendingValue
            FROM sync.SupplierPendingProducts
            WHERE tenant_id = ?
            GROUP BY store_id
        ) p ON p.store_id = st.store_id
        WHERE st.tenant_id = ?
          AND (a.store_id IS NOT NULL OR p.store_id IS NOT NULL)
        ORDER BY st.store_order, st.store_name
    """
    return _run(sql, (tenant_id, tenant_id, tenant_id))


# ---------------------------------------------------------------------------
# Level 2 — Supplier-wise summary within a store.
# ---------------------------------------------------------------------------

def supplier_summary(tenant_id, store_id):
    sql = """
        WITH acks AS (
            SELECT SupplierCode,
                   SUM(Quantity)               AS GivenQty,
                   SUM(AcceptedQty)            AS ReceivedQty,
                   SUM(ISNULL(RejectedQty, 0)) AS RejectQty,
                   SUM(TotalAmount)            AS GivenValue,
                   SUM(AdjustedValue)          AS ReceivedValue,
                   COUNT(*)                    AS Acks
            FROM sync.SupplierAckHeader
            WHERE tenant_id = ? AND store_id = ?
            GROUP BY SupplierCode
        ),
        pend AS (
            SELECT SupplierCode,
                   SUM(Quantity)    AS PendingQty,
                   SUM(TotalAmount) AS PendingValue,
                   COUNT(*)         AS PendingLines
            FROM sync.SupplierPendingProducts
            WHERE tenant_id = ? AND store_id = ?
            GROUP BY SupplierCode
        ),
        codes AS (
            SELECT SupplierCode FROM acks
            UNION
            SELECT SupplierCode FROM pend
        )
        SELECT
            RTRIM(COALESCE(s.suppliername, CAST(c.SupplierCode AS VARCHAR(50)))) AS SupplierName,
            CAST(c.SupplierCode AS VARCHAR(50)) AS SupplierCode,
            ISNULL(a.Acks, 0)          AS Acks,
            ISNULL(a.GivenQty, 0)      AS GivenQty,
            ISNULL(a.ReceivedQty, 0)   AS ReceivedQty,
            ISNULL(a.RejectQty, 0)     AS RejectQty,
            ISNULL(p.PendingQty, 0)    AS PendingQty,
            ISNULL(p.PendingLines, 0)  AS PendingLines,
            ISNULL(a.GivenValue, 0)    AS GivenValue,
            ISNULL(a.ReceivedValue, 0) AS ReceivedValue,
            ISNULL(p.PendingValue, 0)  AS PendingValue
        FROM codes c
        LEFT JOIN acks a ON a.SupplierCode = c.SupplierCode
        LEFT JOIN pend p ON p.SupplierCode = c.SupplierCode
        LEFT JOIN sync.Suppliers s
            ON s.suppliercode = c.SupplierCode
           AND s.tenant_id = ? AND s.store_id = ?
        ORDER BY GivenValue DESC, SupplierName
    """
    return _run(sql, (tenant_id, store_id, tenant_id, store_id, tenant_id, store_id))


# ---------------------------------------------------------------------------
# Level 2b — Pending details (given but not yet claimed) for a supplier.
# ---------------------------------------------------------------------------

def supplier_pending(tenant_id, store_id, supplier_code):
    sql = """
        SELECT
            CAST(p.ProductCode AS VARCHAR(50)) AS ProductCode,
            pr.ProductName,
            p.BatchDescription AS Batch,
            p.ExpiryDate,
            p.AckNumber,
            p.AckDate,
            p.Quantity AS Qty,
            p.FreeQty  AS Free,
            p.Rate,
            p.MRP,
            p.TotalAmount AS Value,
            DATEDIFF(DAY, p.AckDate, GETDATE()) AS DaysPending,
            p.Remarks
        FROM sync.SupplierPendingProducts p
        LEFT JOIN sync.Products pr
            ON pr.tenant_id = p.tenant_id AND pr.store_id = p.store_id
           AND pr.ProductCode = p.ProductCode
        WHERE p.tenant_id = ? AND p.store_id = ? AND p.SupplierCode = ?
        ORDER BY p.AckDate, pr.ProductName
    """
    return _run(sql, (tenant_id, store_id, supplier_code))


# ---------------------------------------------------------------------------
# Level 3 — Ack-wise summary for a supplier (a supplier may have many acks).
# ---------------------------------------------------------------------------

def supplier_acks(tenant_id, store_id, supplier_code):
    sql = """
        SELECT
            h.AckNumber,
            h.AckDate,
            h.Quantity                              AS GivenQty,
            h.AcceptedQty                           AS ReceivedQty,
            ISNULL(h.RejectedQty, 0)                AS RejectQty,
            (h.Quantity - h.AcceptedQty - ISNULL(h.RejectedQty, 0)) AS PendingQty,
            h.TotalAmount                           AS GivenValue,
            h.AdjustedValue                         AS ReceivedValue,
            h.Balance                               AS BalanceValue,
            h.Remarks
        FROM sync.SupplierAckHeader h
        WHERE h.tenant_id = ? AND h.store_id = ? AND h.SupplierCode = ?
        ORDER BY h.AckDate DESC, h.AckNumber DESC
    """
    return _run(sql, (tenant_id, store_id, supplier_code))


# ---------------------------------------------------------------------------
# Level 4 — Product details for one ack.
# ---------------------------------------------------------------------------

def ack_products(tenant_id, store_id, ack_number):
    sql = """
        SELECT
            CAST(d.ProductCode AS VARCHAR(50)) AS ProductCode,
            pr.ProductName,
            d.BatchDescription AS Batch,
            d.ExpiryDate,
            d.Quantity     AS GivenQty,
            d.FreeQty      AS Free,
            d.AcceptedQty  AS ReceivedQty,
            ISNULL(d.RejectedQty, 0) AS RejectQty,
            d.Rate,
            d.Mrp          AS MRP,
            d.TotalAmount  AS Value,
            d.Remarks
        FROM sync.SupplierAckDetail d
        LEFT JOIN sync.Products pr
            ON pr.tenant_id = d.tenant_id AND pr.store_id = d.store_id
           AND pr.ProductCode = d.ProductCode
        WHERE d.tenant_id = ? AND d.store_id = ? AND d.AckNumber = ?
        ORDER BY pr.ProductName
    """
    return _run(sql, (tenant_id, store_id, ack_number))
