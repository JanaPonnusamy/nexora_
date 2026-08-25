"""Data access for the Expiry Report — read-only over the synced Shopaid
supplier-expiry tables in NEXORA_PLATFORM.

Drill-down hierarchy:
  tenant -> store summary -> supplier summary -> ( pending details |
            ack-wise -> ack product details )

Given / Received / Reject come from sync.SupplierAckHeader (Quantity given,
AcceptedQty received, RejectedQty rejected).

Pending faithfully replicates the legacy Shopaid stored procedure
dbo.dsp_SupplierPendingIssueReport, @ProcessMode=0 branch (the mode these
stores use — every synced ack has ProcessMode NULL/0). A UNION of
  (1) SupplierAckHeader+SupplierAckDetail lines whose ack is unsettled
      (ReferenceNumber empty, or Balance<>0 with the rate-mode / partial-
      receipt condition) and which are NOT in SupplierPendingProducts, and
  (2) SupplierPendingProducts (direct-issue pending),
both gated by TransactionValidity + balance filters, ProcessMode=0 and
SeriesSettings.IncludeInReports=1. Validated to the penny against the SP for
NMA (635 rows / 7,336 qty / 169,280.23). Acks are keyed by TransNo (the "Ack
No" the legacy report shows), NOT the numeric AckNumber.

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
# Reusable "pending rows" derived table — a faithful port of the legacy
# dsp_SupplierPendingIssueReport UNION. Exposes tenant_id/store_id/SupplierCode
# so callers can scope + aggregate. No parameters inside; filter it outside.
# ---------------------------------------------------------------------------

_PENDING_ROWS = """
(
    -- Part 1: unsettled acknowledgement detail lines (not already in the
    -- direct-issue pending list).
    SELECT h.tenant_id, h.store_id, h.SupplierCode,
           h.TransNo               AS AckNo,
           h.AckDate               AS AckDate,
           d.ProductCode           AS ProductCode,
           d.BatchDescription      AS Batch,
           d.ExpiryDate            AS ExpiryDate,
           d.Quantity              AS Qty,
           d.FreeQty               AS Free,
           d.PendingQty            AS PendQty,
           d.Rate                  AS Rate,
           d.Mrp                   AS MRP,
           d.TotalAmount           AS Value,
           ISNULL(h.Remarks, '')   AS Remarks
    FROM sync.SupplierAckHeader h
    INNER JOIN sync.SupplierAckDetail d
        ON d.tenant_id = h.tenant_id AND d.store_id = h.store_id
       AND d.TransNo = h.TransNo AND d.AckDate = h.AckDate
    INNER JOIN sync.SeriesSettings ss
        ON ss.tenant_id = h.tenant_id AND ss.store_id = h.store_id
       AND ss.TransID = h.SeriesTransId AND ss.SeriesName = h.SeriesName
    LEFT JOIN (
        SELECT DISTINCT tenant_id, store_id, AckNumber, AckDate
        FROM sync.SupplierPendingProducts
    ) tp ON tp.tenant_id = h.tenant_id AND tp.store_id = h.store_id
        AND tp.AckNumber = h.TransNo AND tp.AckDate = h.AckDate
    WHERE h.TransactionValidity = 0
      AND ( ISNULL(h.ReferenceNumber, '') = ''
            OR (h.Balance <> 0 AND h.RateMode = 3)
            OR (h.Balance <> 0 AND h.RateMode <> 3
                AND ISNULL(h.AcceptedQty, 0) + ISNULL(h.RejectedQty, 0) < ISNULL(h.Quantity, 0)) )
      AND ss.IncludeInReports = 1
      AND ISNULL(h.ProcessMode, 0) = 0
      AND tp.AckNumber IS NULL

    UNION ALL

    -- Part 2: direct-issue pending products (no full ack yet).
    SELECT p.tenant_id, p.store_id, p.SupplierCode,
           h.TransNo               AS AckNo,
           p.AckDate               AS AckDate,
           p.ProductCode           AS ProductCode,
           p.BatchDescription      AS Batch,
           p.ExpiryDate            AS ExpiryDate,
           p.Quantity              AS Qty,
           p.FreeQty               AS Free,
           CAST(0 AS FLOAT)        AS PendQty,
           p.Rate                  AS Rate,
           p.Mrp                   AS MRP,
           p.TotalAmount           AS Value,
           ISNULL(h.Remarks, '')   AS Remarks
    FROM sync.SupplierPendingProducts p
    INNER JOIN sync.SupplierAckHeader h
        ON h.tenant_id = p.tenant_id AND h.store_id = p.store_id
       AND h.TransNo = p.AckNumber AND h.AckDate = p.AckDate
    INNER JOIN sync.SeriesSettings ss
        ON ss.tenant_id = h.tenant_id AND ss.store_id = h.store_id
       AND ss.TransID = h.SeriesTransId AND ss.SeriesName = h.SeriesName
    WHERE h.TransactionValidity = 0
      AND ( (h.AdjustedValue > 0 AND h.Balance <> 0)
            OR (ISNULL(h.ReferenceNumber, '') = '' AND ISNULL(h.Balance, 0) <> 0)
            OR h.AdjustedValue = 0 )
      AND ss.IncludeInReports = 1
      AND ISNULL(h.ProcessMode, 0) = 0
) pend
"""


# ---------------------------------------------------------------------------
# Level 1 — Store-wise summary (all stores of a tenant, totals only).
# ---------------------------------------------------------------------------

def store_summary(tenant_id):
    sql = f"""
        SELECT
            st.store_name  AS StoreName,
            st.store_code  AS StoreCode,
            CAST(st.store_id AS VARCHAR(36)) AS StoreId,
            ISNULL(a.GivenQty, 0)      AS GivenQty,
            ISNULL(a.ReceivedQty, 0)   AS ReceivedQty,
            ISNULL(a.RejectQty, 0)     AS RejectQty,
            ISNULL(pp.PendQty, 0)      AS PendingQty,
            ISNULL(a.GivenValue, 0)    AS GivenValue,
            ISNULL(a.ReceivedValue, 0) AS ReceivedValue,
            ISNULL(pp.PendValue, 0)    AS PendingValue
        FROM dbo.stores st
        LEFT JOIN (
            SELECT store_id,
                   SUM(Quantity)               AS GivenQty,
                   SUM(AcceptedQty)            AS ReceivedQty,
                   SUM(ISNULL(RejectedQty, 0)) AS RejectQty,
                   SUM(TotalAmount)            AS GivenValue,
                   SUM(CASE WHEN Quantity > 0
                            THEN TotalAmount * AcceptedQty / Quantity ELSE 0 END) AS ReceivedValue
            FROM sync.SupplierAckHeader
            WHERE tenant_id = ?
            GROUP BY store_id
        ) a ON a.store_id = st.store_id
        LEFT JOIN (
            SELECT store_id, SUM(Qty) AS PendQty, SUM(Value) AS PendValue
            FROM {_PENDING_ROWS}
            WHERE tenant_id = ?
            GROUP BY store_id
        ) pp ON pp.store_id = st.store_id
        WHERE st.tenant_id = ?
          AND (a.store_id IS NOT NULL OR pp.store_id IS NOT NULL)
        ORDER BY st.store_order, st.store_name
    """
    return _run(sql, (tenant_id, tenant_id, tenant_id))


# ---------------------------------------------------------------------------
# Level 2 — Supplier-wise summary within a store.
# ---------------------------------------------------------------------------

def supplier_summary(tenant_id, store_id):
    sql = f"""
        WITH acks AS (
            SELECT SupplierCode,
                   SUM(Quantity)               AS GivenQty,
                   SUM(AcceptedQty)            AS ReceivedQty,
                   SUM(ISNULL(RejectedQty, 0)) AS RejectQty,
                   SUM(TotalAmount)            AS GivenValue,
                   SUM(CASE WHEN Quantity > 0
                            THEN TotalAmount * AcceptedQty / Quantity ELSE 0 END) AS ReceivedValue,
                   COUNT(*)                    AS Acks
            FROM sync.SupplierAckHeader
            WHERE tenant_id = ? AND store_id = ?
            GROUP BY SupplierCode
        ),
        pend AS (
            SELECT SupplierCode, SUM(Qty) AS PendingQty, SUM(Value) AS PendingValue,
                   COUNT(*) AS PendingLines
            FROM {_PENDING_ROWS}
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
# Level 2b — Pending details (legacy Supplier Pending Issue Report) for a
# supplier. Rows come straight from the legacy pending UNION.
# ---------------------------------------------------------------------------

def supplier_pending(tenant_id, store_id, supplier_code):
    sql = f"""
        SELECT
            pend.AckNo                          AS AckNumber,
            pend.AckDate                        AS AckDate,
            CAST(pend.ProductCode AS VARCHAR(50)) AS ProductCode,
            pr.ProductName                      AS ProductName,
            pend.Batch                          AS Batch,
            pend.ExpiryDate                     AS ExpiryDate,
            pend.Qty                            AS Qty,
            pend.Free                           AS Free,
            pend.Rate                           AS Rate,
            pend.MRP                            AS MRP,
            pend.Value                          AS Value,
            DATEDIFF(DAY, pend.AckDate, GETDATE()) AS DaysPending,
            pend.Remarks                        AS Remarks
        FROM {_PENDING_ROWS}
        LEFT JOIN sync.Products pr
            ON pr.tenant_id = pend.tenant_id AND pr.store_id = pend.store_id
           AND pr.ProductCode = pend.ProductCode
        WHERE pend.tenant_id = ? AND pend.store_id = ? AND pend.SupplierCode = ?
        ORDER BY pend.AckDate, pr.ProductName
    """
    return _run(sql, (tenant_id, store_id, supplier_code))


# ---------------------------------------------------------------------------
# Level 2c — Pending by month: month totals + a month's detail (all suppliers).
# ---------------------------------------------------------------------------

def pending_months(tenant_id, store_id):
    """Per-month pending totals for a store (all suppliers), newest first."""
    sql = f"""
        SELECT
            CONVERT(CHAR(7), pend.AckDate, 126) AS MonthKey,
            LEFT(DATENAME(MONTH, pend.AckDate), 3) + ' '
                + CAST(YEAR(pend.AckDate) AS VARCHAR(4)) AS Period,
            COUNT(*)         AS Lines,
            SUM(pend.Qty)    AS PendingQty,
            SUM(pend.Value)  AS PendingValue
        FROM {_PENDING_ROWS}
        WHERE pend.tenant_id = ? AND pend.store_id = ?
        GROUP BY CONVERT(CHAR(7), pend.AckDate, 126),
                 LEFT(DATENAME(MONTH, pend.AckDate), 3),
                 YEAR(pend.AckDate), MONTH(pend.AckDate)
        ORDER BY YEAR(pend.AckDate) DESC, MONTH(pend.AckDate) DESC
    """
    return _run(sql, (tenant_id, store_id))


def pending_by_month(tenant_id, store_id, month):
    """All pending detail lines for a store in one month (month = 'yyyy-MM')."""
    sql = f"""
        SELECT
            RTRIM(COALESCE(s.suppliername, CAST(pend.SupplierCode AS VARCHAR(50)))) AS SupplierName,
            pend.AckNo                          AS AckNumber,
            pend.AckDate                        AS AckDate,
            CAST(pend.ProductCode AS VARCHAR(50)) AS ProductCode,
            pr.ProductName                      AS ProductName,
            pend.Batch                          AS Batch,
            pend.ExpiryDate                     AS ExpiryDate,
            pend.Qty                            AS Qty,
            pend.Free                           AS Free,
            pend.Rate                           AS Rate,
            pend.MRP                            AS MRP,
            pend.Value                          AS Value,
            DATEDIFF(DAY, pend.AckDate, GETDATE()) AS DaysPending,
            pend.Remarks                        AS Remarks
        FROM {_PENDING_ROWS}
        LEFT JOIN sync.Suppliers s
            ON s.suppliercode = pend.SupplierCode
           AND s.tenant_id = pend.tenant_id AND s.store_id = pend.store_id
        LEFT JOIN sync.Products pr
            ON pr.tenant_id = pend.tenant_id AND pr.store_id = pend.store_id
           AND pr.ProductCode = pend.ProductCode
        WHERE pend.tenant_id = ? AND pend.store_id = ?
          AND CONVERT(CHAR(7), pend.AckDate, 126) = ?
        ORDER BY SupplierName, pend.AckDate, pr.ProductName
    """
    return _run(sql, (tenant_id, store_id, month))


# ---------------------------------------------------------------------------
# Level 3 — Ack-wise summary for a supplier ("Ack No" = TransNo).
# ---------------------------------------------------------------------------

def supplier_acks(tenant_id, store_id, supplier_code):
    sql = """
        SELECT
            h.TransNo                               AS AckNumber,
            h.AckDate                               AS AckDate,
            h.Quantity                              AS GivenQty,
            h.AcceptedQty                           AS ReceivedQty,
            ISNULL(h.RejectedQty, 0)                AS RejectQty,
            (h.Quantity - h.AcceptedQty - ISNULL(h.RejectedQty, 0)) AS PendingQty,
            h.TotalAmount                           AS GivenValue,
            CASE WHEN h.Quantity > 0
                 THEN h.TotalAmount * h.AcceptedQty / h.Quantity ELSE 0 END AS ReceivedValue,
            CASE WHEN h.Quantity > 0
                 THEN h.TotalAmount * (h.Quantity - h.AcceptedQty - ISNULL(h.RejectedQty, 0)) / h.Quantity
                 ELSE 0 END AS PendingValue,
            h.Remarks
        FROM sync.SupplierAckHeader h
        WHERE h.tenant_id = ? AND h.store_id = ? AND h.SupplierCode = ?
        ORDER BY h.AckDate DESC, h.TransNo DESC
    """
    return _run(sql, (tenant_id, store_id, supplier_code))


# ---------------------------------------------------------------------------
# Level 4 — Product details for one ack (linked by TransNo).
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
        WHERE d.tenant_id = ? AND d.store_id = ? AND d.TransNo = ?
        ORDER BY pr.ProductName
    """
    return _run(sql, (tenant_id, store_id, ack_number))
