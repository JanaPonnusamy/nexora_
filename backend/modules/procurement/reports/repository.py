"""Read-only data access for the integrated Pharmacy Reports module."""

from config.database import get_connection
from repositories.store_repository import StoreRepository
from modules.procurement._dbutil import rows_to_dicts


def _run(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return rows_to_dicts(cursor)
    finally:
        conn.close()


def _serialize_store(row):
    if row is None:
        return None
    return {
        "store_id": str(row[0]),
        "tenant_id": str(row[1]),
        "store_code": row[2],
        "store_name": row[3],
        "server_name": row[4],
        "database_name": row[5],
        "is_active": bool(row[6]),
    }


def active_stores(tenant_id):
    rows = StoreRepository().get_by_tenant(tenant_id)
    return [
        _serialize_store(row)
        for row in rows
        if bool(row[6])
    ]


def store_by_id(tenant_id, store_id):
    row = StoreRepository().get_by_id(store_id)
    if not row:
        return None
    if str(row[1]) != str(tenant_id):
        return None
    if not bool(row[6]):
        return None
    return _serialize_store(row)


def product_monthly_summary(tenant_id, store_id, from_month, to_month):
    sql = """
        SELECT
            MonthOfStatistics,
            SUM(SaleValue) AS Sales,
            SUM(PurchaseValue) AS Purchase,
            SUM(PurchaseReturnQuantity) AS PurchaseReturn,
            SUM(OpeningStockValue) AS OpeningStock,
            SUM(TransferInQuantity) AS TransferIn,
            SUM(TransferOutQuantity) AS TransferOut,
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
