"""Read-only data access for the integrated Pharmacy Reports module."""

from pathlib import Path

import pyodbc

from config.database import get_connection
from modules.legacy_order.database import branch_connection_string
from modules.procurement._dbutil import rows_to_dicts
from repositories.store_repository import StoreRepository
from services.store_crypto_service import StoreCryptoService

try:
    from store_agent.fernet_key_service import FernetKeyService
except ModuleNotFoundError:
    class FernetKeyService:
        KEY_FILE = Path(__file__).resolve().parents[4] / "store_agent" / "config" / "fernet.key"

        def load_key(self):
            return self.KEY_FILE.read_bytes()

        def key_exists(self):
            return self.KEY_FILE.exists()


def _run(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return rows_to_dicts(cursor)
    finally:
        conn.close()


def _normalize_source(source):
    normalized = (source or "NEXORA").strip().upper()
    return "STORE_DB" if normalized == "STORE_DB" else "NEXORA"


def _live_store_config(store_id):
    row = StoreRepository().get_agent_config(store_id)
    if not row:
        raise ValueError("Store configuration not found.")
    if not row[8]:
        raise ValueError("Store is inactive.")

    server_name = row[2]
    database_name = row[3]
    username = row[4]
    password_encrypted = row[5]

    if not server_name or not database_name:
        raise ValueError("Store server/database is not configured.")
    if not username or not password_encrypted:
        raise ValueError("Store DB credentials are not configured.")

    key_service = FernetKeyService()
    if not key_service.key_exists():
        raise ValueError("Store decryption key not found on the server.")

    password = StoreCryptoService.decrypt_password(
        password_encrypted,
        key_service.load_key(),
    )
    return {
        "server_name": server_name,
        "database_name": database_name,
        "username": username,
        "password": password,
    }


def _run_store_db(store_id, sql, params):
    cfg = _live_store_config(store_id)
    conn = pyodbc.connect(
        branch_connection_string(
            cfg["server_name"],
            cfg["database_name"],
            cfg["username"],
            cfg["password"],
        ),
        timeout=30,
    )
    try:
        conn.timeout = 300
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


def product_monthly_summary(tenant_id, store_id, from_month, to_month, source="NEXORA"):
    source = _normalize_source(source)
    if source == "STORE_DB":
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
            FROM ProductTrans
            WHERE MonthOfStatistics BETWEEN CAST(? AS DATETIME)
                AND EOMONTH(CAST(? AS DATETIME))
            GROUP BY MonthOfStatistics
            ORDER BY MonthOfStatistics
        """
        return _run_store_db(store_id, sql, (f"{from_month}-01", f"{to_month}-01"))

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


def supplier_monthly_summary(tenant_id, store_id, from_month, to_month, source="NEXORA"):
    source = _normalize_source(source)
    if source == "STORE_DB":
        sql = """
            SELECT
                MonthOfStatistics,
                SUM(ClosingBalance) AS PendingAmount,
                SUM(NoOfPendingInvoices) AS PendingInvoices
            FROM Suppliertrans
            WHERE MonthOfStatistics BETWEEN CAST(? AS DATETIME)
                AND EOMONTH(CAST(? AS DATETIME))
            GROUP BY MonthOfStatistics
            ORDER BY MonthOfStatistics
        """
        return _run_store_db(store_id, sql, (f"{from_month}-01", f"{to_month}-01"))

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
