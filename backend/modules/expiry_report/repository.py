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
# Unified pivot: date range + status (all/received/pending/rejected) x
# group_by (summary/ack/month/supplier/product). Given/Received/Rejected come
# from the ack detail lines; Pending from the legacy-SP pending set. Both are
# aggregated by the chosen dimension and merged in Python.
# ---------------------------------------------------------------------------

def date_bounds(tenant_id, store_id=None):
    """Oldest pending AckDate for the scope (default 'from' date)."""
    where = "pend.tenant_id = ?"
    params = [tenant_id]
    if store_id:
        where += " AND pend.store_id = ?"
        params.append(store_id)
    sql = f"SELECT MIN(pend.AckDate) AS Oldest FROM {_PENDING_ROWS} WHERE {where}"
    _, rows = _run(sql, tuple(params))
    val = rows[0]["Oldest"] if rows else None
    return {"oldest_pending": val.strftime("%Y-%m-%d") if val else None}


def _dim_ack(group_by):
    """(key_expr, label_expr, group_by_expr, extra_select, joins) for ack base."""
    if group_by == "summary":
        return ("CAST(h.store_id AS VARCHAR(36))", "MAX(st.store_name)", "h.store_id",
                "", "LEFT JOIN dbo.stores st ON st.store_id = h.store_id")
    if group_by == "ack":
        return ("h.TransNo", "h.TransNo", "h.TransNo",
                ", MIN(h.AckDate) AS AckDate, MAX(RTRIM(s.suppliername)) AS Supplier",
                "LEFT JOIN sync.Suppliers s ON s.suppliercode=h.SupplierCode AND s.tenant_id=h.tenant_id AND s.store_id=h.store_id")
    if group_by == "month":
        return ("CONVERT(CHAR(7), h.AckDate, 126)",
                "MAX(LEFT(DATENAME(MONTH,h.AckDate),3)+' '+CAST(YEAR(h.AckDate) AS VARCHAR(4)))",
                "CONVERT(CHAR(7), h.AckDate, 126)", ", MIN(h.AckDate) AS SortDate", "")
    if group_by == "supplier":
        return ("CAST(h.SupplierCode AS VARCHAR(50))", "MAX(RTRIM(s.suppliername))", "h.SupplierCode",
                "", "LEFT JOIN sync.Suppliers s ON s.suppliercode=h.SupplierCode AND s.tenant_id=h.tenant_id AND s.store_id=h.store_id")
    # product
    return ("CAST(d.ProductCode AS VARCHAR(50))", "MAX(pr.ProductName)", "d.ProductCode",
            "", "LEFT JOIN sync.Products pr ON pr.ProductCode=d.ProductCode AND pr.tenant_id=d.tenant_id AND pr.store_id=d.store_id")


def _dim_pending(group_by):
    """(key_expr, label_expr, group_by_expr, extra_select, joins) for pending base."""
    if group_by == "summary":
        return ("CAST(pend.store_id AS VARCHAR(36))", "MAX(st.store_name)", "pend.store_id",
                "", "LEFT JOIN dbo.stores st ON st.store_id = pend.store_id")
    if group_by == "ack":
        return ("pend.AckNo", "pend.AckNo", "pend.AckNo",
                ", MIN(pend.AckDate) AS AckDate, MAX(RTRIM(s.suppliername)) AS Supplier",
                "LEFT JOIN sync.Suppliers s ON s.suppliercode=pend.SupplierCode AND s.tenant_id=pend.tenant_id AND s.store_id=pend.store_id")
    if group_by == "month":
        return ("CONVERT(CHAR(7), pend.AckDate, 126)",
                "MAX(LEFT(DATENAME(MONTH,pend.AckDate),3)+' '+CAST(YEAR(pend.AckDate) AS VARCHAR(4)))",
                "CONVERT(CHAR(7), pend.AckDate, 126)", ", MIN(pend.AckDate) AS SortDate", "")
    if group_by == "supplier":
        return ("CAST(pend.SupplierCode AS VARCHAR(50))", "MAX(RTRIM(s.suppliername))", "pend.SupplierCode",
                "", "LEFT JOIN sync.Suppliers s ON s.suppliercode=pend.SupplierCode AND s.tenant_id=pend.tenant_id AND s.store_id=pend.store_id")
    return ("CAST(pend.ProductCode AS VARCHAR(50))", "MAX(pr.ProductName)", "pend.ProductCode",
            "", "LEFT JOIN sync.Products pr ON pr.ProductCode=pend.ProductCode AND pr.tenant_id=pend.tenant_id AND pr.store_id=pend.store_id")


def _ack_agg(tenant_id, store_id, from_date, to_date, group_by):
    keyx, labelx, groupx, extra, join = _dim_ack(group_by)
    where = ["h.tenant_id = ?", "h.TransactionValidity = 0",
             "CAST(h.AckDate AS DATE) BETWEEN ? AND ?"]
    params = [tenant_id, from_date, to_date]
    if store_id:
        where.append("h.store_id = ?"); params.append(store_id)
    sql = f"""
        SELECT {keyx} AS GroupKey, {labelx} AS Label{extra},
               SUM(d.Quantity) AS gq, SUM(d.TotalAmount) AS gv,
               SUM(d.AcceptedQty) AS rq,
               SUM(CASE WHEN d.Quantity>0 THEN d.TotalAmount*d.AcceptedQty/d.Quantity ELSE 0 END) AS rv,
               SUM(ISNULL(d.RejectedQty,0)) AS jq,
               SUM(CASE WHEN d.Quantity>0 THEN d.TotalAmount*ISNULL(d.RejectedQty,0)/d.Quantity ELSE 0 END) AS jv
        FROM sync.SupplierAckHeader h
        INNER JOIN sync.SupplierAckDetail d
            ON d.tenant_id=h.tenant_id AND d.store_id=h.store_id
           AND d.TransNo=h.TransNo AND d.AckDate=h.AckDate
        {join}
        WHERE {' AND '.join(where)}
        GROUP BY {groupx}
    """
    _, rows = _run(sql, tuple(params))
    return rows


def _pending_agg(tenant_id, store_id, from_date, to_date, group_by):
    keyx, labelx, groupx, extra, join = _dim_pending(group_by)
    where = ["pend.tenant_id = ?", "CAST(pend.AckDate AS DATE) BETWEEN ? AND ?"]
    params = [tenant_id, from_date, to_date]
    if store_id:
        where.append("pend.store_id = ?"); params.append(store_id)
    sql = f"""
        SELECT {keyx} AS GroupKey, {labelx} AS Label{extra},
               SUM(pend.Qty) AS pq, SUM(pend.Value) AS pv
        FROM {_PENDING_ROWS}
        {join}
        WHERE {' AND '.join(where)}
        GROUP BY {groupx}
    """
    _, rows = _run(sql, tuple(params))
    return rows


def expiry_data(tenant_id, store_id, from_date, to_date, status, group_by):
    """Merged pivot rows. Always returns every measure; the service picks the
    columns to show for the chosen status."""
    need_ack = status in ("all", "received", "rejected")
    need_pend = status in ("all", "pending")
    ack = _ack_agg(tenant_id, store_id, from_date, to_date, group_by) if need_ack else []
    pend = _pending_agg(tenant_id, store_id, from_date, to_date, group_by) if need_pend else []

    merged = {}
    def slot(r):
        k = r["GroupKey"]
        m = merged.get(k)
        if not m:
            m = {"GroupKey": k, "Group": (r.get("Label") or k),
                 "AckDate": r.get("AckDate"), "Supplier": r.get("Supplier"),
                 "SortDate": r.get("SortDate"),
                 "GivenQty": 0, "GivenValue": 0, "ReceivedQty": 0, "ReceivedValue": 0,
                 "RejectQty": 0, "RejectValue": 0, "PendingQty": 0, "PendingValue": 0}
            merged[k] = m
        return m
    for r in ack:
        m = slot(r)
        m["GivenQty"] += r["gq"] or 0; m["GivenValue"] += r["gv"] or 0
        m["ReceivedQty"] += r["rq"] or 0; m["ReceivedValue"] += r["rv"] or 0
        m["RejectQty"] += r["jq"] or 0; m["RejectValue"] += r["jv"] or 0
    for r in pend:
        m = slot(r)
        m["PendingQty"] += r["pq"] or 0; m["PendingValue"] += r["pv"] or 0

    rows = list(merged.values())
    # Status-specific row filter (drop empty rows for single-status views).
    if status == "received":
        rows = [r for r in rows if (r["ReceivedQty"] or 0) != 0]
    elif status == "rejected":
        rows = [r for r in rows if (r["RejectQty"] or 0) != 0]
    elif status == "pending":
        rows = [r for r in rows if (r["PendingQty"] or 0) != 0]

    # Ordering: month by date desc; everything else by the dominant value desc.
    if group_by == "month":
        rows.sort(key=lambda r: str(r.get("SortDate") or ""), reverse=True)
    else:
        sortkey = {"received": "ReceivedValue", "rejected": "RejectValue",
                   "pending": "PendingValue"}.get(status, "GivenValue")
        rows.sort(key=lambda r: float(r.get(sortkey) or 0), reverse=True)
    return rows


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
