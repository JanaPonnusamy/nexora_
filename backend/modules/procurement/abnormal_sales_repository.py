"""Bill-level sales reads and DontConsiderInOrder writes for abnormal-sale review.

Two sources, one shape (product_code, bill_no, bill_date, qty, dont_consider):
  * platform -- NEXORA_PLATFORM sync.ProductSaleInformation, the products of
    one procurement refresh (Procurement screen / decision engine);
  * legacy   -- OrderNMC ProductSaleInformation, the store's open
    OrderManagement products (Order Workspace / legacy order SQL).

Bills are valid retail sales only (SeriesTransID = 1, TransactionValidity = 0),
quantity > 0, grouped per product per bill (BNumber + bill date). A bill is
"do not consider" when every line of that product on it is flagged.
"""

from config.database import get_connection
from modules.legacy_order import database as legacy_database
from modules.procurement._dbutil import as_uid as _as_uid, rows_to_dicts as _rows_to_dicts


def platform_bills(tenant_id, refresh_id, since):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH codes AS (
                SELECT DISTINCT oi.store_id, TRY_CAST(oi.product_code AS INT) AS code
                FROM procurement.procurement_order_items oi
                WHERE oi.tenant_id = ? AND oi.refresh_id = ? AND oi.is_deleted = 0
            )
            SELECT CAST(psi.ProductCode AS VARCHAR(100)) AS product_code,
                   RTRIM(psi.BNumber) AS bill_no,
                   CAST(psi.TransactionDate AS DATE) AS bill_date,
                   SUM(psi.Quantity) AS qty,
                   MIN(CAST(ISNULL(psi.DontConsiderInOrder, 0) AS INT)) AS dont_consider
            FROM codes c
            INNER JOIN sync.ProductSaleInformation psi
                ON psi.tenant_id = ? AND psi.store_id = c.store_id AND psi.ProductCode = c.code
            WHERE c.code IS NOT NULL
              AND psi.SeriesTransID = 1 AND ISNULL(psi.TransactionValidity, 0) = 0
              AND psi.TransactionDate >= ? AND psi.Quantity > 0
            GROUP BY psi.ProductCode, RTRIM(psi.BNumber), CAST(psi.TransactionDate AS DATE)
            """,
            (tenant_id, refresh_id, tenant_id, since),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def platform_customers(tenant_id, store_id, bills):
    """{(bill_no, bill_date): customer} for the given (bill_no, bill_date) pairs."""
    if not bills:
        return {}
    conn = get_connection()
    try:
        cursor = conn.cursor()
        out = {}
        nos = sorted({b[0] for b in bills})
        for i in range(0, len(nos), 500):
            chunk = nos[i:i + 500]
            cursor.execute(
                f"""
                SELECT RTRIM(BNumber), CAST(BillDate AS DATE), MAX(CustomerName)
                FROM sync.SaleInformation
                WHERE tenant_id = ? AND store_id = ? AND BNumber IN ({", ".join("?" for _ in chunk)})
                GROUP BY RTRIM(BNumber), CAST(BillDate AS DATE)
                """,
                (tenant_id, store_id, *chunk),
            )
            for bill_no, bill_date, customer in cursor.fetchall():
                out[(bill_no, str(bill_date))] = customer
        return out
    finally:
        conn.close()


def legacy_bills(store_name, since):
    sql = """
        WITH prods AS (
            SELECT DISTINCT productcode FROM ordermanagement WHERE storename = ? AND status = 0
        )
        SELECT CAST(ps.ProductCode AS VARCHAR(100)) AS product_code,
               RTRIM(ps.Bnumber) AS bill_no,
               CAST(ps.TransactionDate AS DATE) AS bill_date,
               SUM(ps.Quantity) AS qty,
               MIN(CAST(ISNULL(ps.DontConsiderInOrder, 0) AS INT)) AS dont_consider
        FROM ProductSaleInformation ps
        INNER JOIN prods p ON p.productcode = ps.ProductCode
        WHERE ps.StoreName = ? AND ps.SeriesTransID = 1 AND ps.TransactionValidity = 0
          AND ps.TransactionDate >= ? AND ps.Quantity > 0
        GROUP BY ps.ProductCode, RTRIM(ps.Bnumber), CAST(ps.TransactionDate AS DATE)
    """
    with legacy_database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name, store_name, since)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def legacy_customers(store_name, bills):
    if not bills:
        return {}
    out = {}
    nos = sorted({b[0] for b in bills})
    with legacy_database.get_central_connection() as conn:
        cursor = conn.cursor()
        for i in range(0, len(nos), 500):
            chunk = nos[i:i + 500]
            cursor.execute(
                f"""
                SELECT RTRIM(BNumber), CAST(BillDate AS DATE), MAX(CustomerName)
                FROM SaleInformation
                WHERE StoreName = ? AND BNumber IN ({", ".join("?" for _ in chunk)})
                GROUP BY RTRIM(BNumber), CAST(BillDate AS DATE)
                """,
                store_name, *chunk,
            )
            for bill_no, bill_date, customer in cursor.fetchall():
                out[(bill_no, str(bill_date))] = customer
    return out


def set_platform_flag(tenant_id, store_id, product_code, bill_no, bill_date, value):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sync.ProductSaleInformation
            SET DontConsiderInOrder = ?
            WHERE tenant_id = ? AND store_id = ?
              AND ProductCode = TRY_CAST(? AS INT)
              AND RTRIM(BNumber) = ?
              AND CAST(TransactionDate AS DATE) = CAST(? AS DATE)
              AND SeriesTransID = 1 AND ISNULL(TransactionValidity, 0) = 0
            """,
            (1 if value else 0, tenant_id, store_id, product_code, bill_no, bill_date),
        )
        updated = cursor.rowcount
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_legacy_flag(store_name, product_code, bill_no, bill_date, value):
    with legacy_database.get_central_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE ProductSaleInformation
            SET DontConsiderInOrder = ?
            WHERE StoreName = ?
              AND ProductCode = TRY_CAST(? AS INT)
              AND RTRIM(Bnumber) = ?
              AND CAST(TransactionDate AS DATE) = CAST(? AS DATE)
              AND SeriesTransID = 1 AND TransactionValidity = 0
            """,
            1 if value else 0, store_name, product_code, bill_no, bill_date,
        )
        updated = cursor.rowcount
        conn.commit()
        return updated


def store_by_id(store_id):
    store_id = _as_uid(store_id)
    if not store_id:
        return None
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT tenant_id, store_id, store_code FROM dbo.stores WHERE store_id = ?", (store_id,))
        rows = _rows_to_dicts(cursor)
        return rows[0] if rows else None
    finally:
        conn.close()


