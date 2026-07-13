"""Reads from the legacy OrderNMC database."""
from modules.legacy_order import database


def _row_to_store(row):
    return {
        "store_code": str(int(row.StoreCode)) if row.StoreCode is not None else "",
        "store_name": row.StoreName,
        "server_name": row.ServerName or "",
        "database": getattr(row, "Database") or "",
        "username": row.UserName or "",
        "password": row.Password or "",
        "is_active": bool(row.IsActive),
        "last_sync_time": row.LastSyncTime,
        "last_sync_status": row.LastSyncStatus,
    }


def list_stores(active_only=True):
    """Branches configured in dbo.Stores -- the source DBs the legacy app synced."""
    sql = (
        "SELECT StoreCode, StoreName, ServerName, UserName, Password, [Database], "
        "IsActive, LastSyncTime, LastSyncStatus FROM Stores"
    )
    if active_only:
        sql += " WHERE IsActive = 1"
    sql += " ORDER BY StoreCode"

    with database.get_central_connection() as conn:
        return [_row_to_store(r) for r in conn.cursor().execute(sql)]


def get_store(store_name):
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT StoreCode, StoreName, ServerName, UserName, Password, [Database], "
            "IsActive, LastSyncTime, LastSyncStatus FROM Stores WHERE StoreName = ?",
            store_name,
        ).fetchone()
    return _row_to_store(row) if row else None


def mark_sync_result(store_name, status):
    with database.get_central_connection() as conn:
        conn.cursor().execute(
            "UPDATE Stores SET LastSyncTime = GETDATE(), LastSyncStatus = ? "
            "WHERE StoreName = ?",
            status, store_name,
        )
        conn.commit()


def test_branch_connection(store):
    """Port of the Syncbtn_Click pre-flight: fail early with a clear message."""
    try:
        conn = database.get_branch_connection(
            store["server_name"], store["database"],
            store["username"], store["password"], timeout=8,
        )
        conn.close()
        return True, None
    except Exception as exc:
        return False, str(exc)


def order_summary(store_name):
    """Current OrderManagement rows for a store -- what the VB grid showed."""
    sql = (
        "SELECT OrderId, ProductCode, ProductName, TotalStock, SaleUnit, SLSQty, "
        "MinQty, MaxQty, OrderQty, OrgOrderQty, WantedType, ProductTypeName, "
        "Frequence, MRP, PurchasePrice, UnitDescription, SubLocation, "
        "LastSaleDate, LastReceivedDate, WantedDate, Status, Remarks "
        "FROM OrderManagement WHERE StoreName = ? ORDER BY ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
