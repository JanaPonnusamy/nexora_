"""Read-only data access for the integrated Pharmacy Reports module."""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts


def _run(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return rows_to_dicts(cursor)
    finally:
        conn.close()


def active_stores(tenant_id):
    sql = """
        SELECT
            CAST(store_id AS VARCHAR(50)) AS store_id,
            CAST(tenant_id AS VARCHAR(50)) AS tenant_id,
            store_code,
            store_name,
            server_name,
            database_name,
            is_active
        FROM dbo.stores
        WHERE tenant_id = ? AND is_active = 1
        ORDER BY store_code
    """
    return _run(sql, (tenant_id,))


def store_by_id(tenant_id, store_id):
    sql = """
        SELECT
            CAST(store_id AS VARCHAR(50)) AS store_id,
            CAST(tenant_id AS VARCHAR(50)) AS tenant_id,
            store_code,
            store_name,
            server_name,
            database_name,
            is_active
        FROM dbo.stores
        WHERE tenant_id = ? AND store_id = ? AND is_active = 1
    """
    rows = _run(sql, (tenant_id, store_id))
    return rows[0] if rows else None


def product_monthly_summary(tenant_id, store_id, from_month, to_month):
    sql = """
        SELECT
            MonthOfStatistics,
            SUM(SaleValueWithoutReturn) AS Sales,
            SUM(PurchaseValueWithoutReturn) AS Purchase,
            SUM(PurchaseReturnValue) AS PurchaseReturn,
            SUM(OpeningStockValue) AS OpeningStock,
            SUM(TransferInValue) AS TransferIn,
            SUM(TransferOutValue) AS TransferOut,
            SUM(AdjustmentValue) AS Adjustment,
            SUM(StockValueAtCostPrice) AS ClosingStock,
            SUM(CostOfSales) AS CostOfSales
        FROM sync.ProductTrans
        WHERE tenant_id = ?
          AND store_id = ?
          AND MonthOfStatistics BETWEEN CAST(? AS DATETIME)
              AND EOMONTH(CAST(? AS DATETIME))
        GROUP BY MonthOfStatistics
        ORDER BY MonthOfStatistics
    """
    return _run(sql, (tenant_id, store_id, f"{from_month}-01", f"{to_month}-01"))


def supplier_monthly_summary(tenant_id, store_id, from_month, to_month):
    sql = """
        SELECT
            MonthOfStatistics,
            SUM(ClosingBalance) AS PendingAmount,
            SUM(NoOfPendingInvoices) AS PendingInvoices
        FROM sync.SupplierTrans
        WHERE tenant_id = ?
          AND store_id = ?
          AND MonthOfStatistics BETWEEN CAST(? AS DATETIME)
              AND EOMONTH(CAST(? AS DATETIME))
        GROUP BY MonthOfStatistics
        ORDER BY MonthOfStatistics
    """
    return _run(sql, (tenant_id, store_id, f"{from_month}-01", f"{to_month}-01"))
