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
        # This store's OWN code for the HO/NMW supplier (dbo.Stores.Ho_code) --
        # e.g. NMS/NMA use '94', NMC uses 'ST_2', NMG uses '99'. NOT the same
        # string across stores, so distribution must look this up per target
        # rather than writing the literal source store name as suppliercode.
        "ho_code": getattr(row, "Ho_code", None),
    }


def list_stores(active_only=True):
    """Branches configured in dbo.Stores -- the source DBs the legacy app synced."""
    sql = (
        "SELECT StoreCode, StoreName, ServerName, UserName, Password, [Database], "
        "IsActive, LastSyncTime, LastSyncStatus, Ho_code FROM Stores"
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
            "IsActive, LastSyncTime, LastSyncStatus, Ho_code FROM Stores WHERE StoreName = ?",
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


# --------------------------------------------------------------------------
# Internal Supplier Stock Distribution -- one branch's own stock (the HO
# store, e.g. NMW) pushed into the central SupplierStock table for every
# other branch, exactly the shape the old VB app read for supplier ordering.
# --------------------------------------------------------------------------

_MASTER_STOCK_SQL = """
WITH LatestPT AS (
    SELECT
        pt.*,
        ROW_NUMBER() OVER (
            PARTITION BY pt.ProductCode
            ORDER BY pt.ID DESC
        ) AS rn
    FROM PURCHASETRANS pt
),
TotalStockPerProduct AS (
    SELECT
        b.ProductCode,
        SUM(b.Stock) AS TotalStock
    FROM BATCHES b
    GROUP BY b.ProductCode
)
SELECT
    p.ProductCode,
    p.ProductName,
    tsp.TotalStock AS stock,
    ROUND(
        CASE
            WHEN pt.PurchasePrice > 0
            THEN ((pt.PurchasePrice - pt.ItemCost) * 100.0 / pt.PurchasePrice)
            ELSE 0
        END,
        2
    ) AS ProductDiscPercent
FROM PRODUCTS p
INNER JOIN TotalStockPerProduct tsp
    ON tsp.ProductCode = p.ProductCode
LEFT JOIN LatestPT pt
    ON pt.ProductCode = p.ProductCode
   AND pt.rn = 1
WHERE tsp.TotalStock > 0
ORDER BY p.ProductName
"""


def branch_stock(store):
    """Run the master export query directly against a branch's own DB
    (PRODUCTS/BATCHES/PURCHASETRANS) -- the store's real, current stock."""
    conn = database.get_branch_connection(
        store["server_name"], store["database"], store["username"], store["password"],
    )
    try:
        cur = conn.cursor()
        cur.execute(_MASTER_STOCK_SQL)
        return [
            {
                "code": r.ProductCode,
                "name": r.ProductName,
                "stock": float(r.stock or 0),
                "disc_percent": float(r.ProductDiscPercent or 0),
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def replace_supplier_stock(target_store_name, supplier_code, rows):
    """REPLACE this supplier's rows for one branch in the central
    OrderNMC.SupplierStock table -- the same table/shape the legacy Excel
    import wrote, storename-scoped, so the branch's own order screen sees it
    exactly like any other supplier upload."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM SupplierStock WHERE storename = ? AND suppliercode = ?",
            (target_store_name, supplier_code),
        )
        if rows:
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO SupplierStock "
                "(suppliercode, supplierproductcode, supplierproductname, mrp, ptr, "
                "stock, discound, packing, storename, sch, free, transactiondate, minqty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)",
                [
                    (supplier_code, r["code"], r["name"], None, None,
                     r["stock"], str(r["disc_percent"]), None, target_store_name, 0, 0, None)
                    for r in rows
                ],
            )
        conn.commit()
        return len(rows)


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


def previous_orders(store_name):
    """Match Form1.LoadOrderID: recent two days, otherwise latest five."""
    recent_sql = (
        "SELECT DISTINCT StoreName, OrderId, WantedDate FROM OrderManagementBackup "
        "WHERE CAST(WantedDate AS date) >= DATEADD(day, -1, CAST(GETDATE() AS date)) "
        "AND StoreName = ? ORDER BY WantedDate DESC"
    )
    fallback_sql = (
        "SELECT DISTINCT TOP 5 StoreName, OrderId, WantedDate FROM OrderManagementBackup "
        "WHERE StoreName = ? ORDER BY WantedDate DESC"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        rows = cur.execute(recent_sql, store_name).fetchall()
        if not rows:
            rows = cur.execute(fallback_sql, store_name).fetchall()
        return [
            {"store_name": row.StoreName, "order_id": int(row.OrderId), "wanted_date": row.WantedDate}
            for row in rows
        ]


def compare_previous_order(store_name, order_id):
    """Port Form1.CompareOrderManagement's three comparison rules atomically."""
    remarks = f"Compare Order with {order_id}"
    sql = """
    UPDATE om SET om.OrQty = omb.OrQty, om.OrSupplier = omb.OrSupplier,
        om.Status = 2, om.Remarks = ?
    FROM OrderManagement om INNER JOIN OrderManagementBackup omb
        ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
    WHERE omb.OrderId = ? AND omb.Status = 1 AND omb.OrSupplier IS NOT NULL
        AND omb.OrQty IS NOT NULL AND om.StoreName = ?;
    UPDATE om SET om.Status = 2, om.Remarks = ?
    FROM OrderManagement om INNER JOIN OrderManagementBackup omb
        ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
    WHERE omb.OrderId = ? AND omb.Status = 0 AND om.StoreName = ?
        AND ((omb.OrSupplier IS NOT NULL AND omb.OrQty IS NOT NULL) OR omb.OrderQty = 0);
    UPDATE om SET om.OrderQty = (om.OrgOrderQty - omb.OrQty), om.Status = 0,
        om.Remarks = 'After Order Sold', om.WantedType = 'After Order Sold'
    FROM OrderManagement om INNER JOIN OrderManagementBackup omb
        ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
    WHERE omb.OrderId = ? AND omb.TotalStock > om.TotalStock AND omb.OrQty IS NOT NULL
        AND (om.OrgOrderQty - omb.OrQty) > 0 AND om.StoreName = ?;
    """
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, remarks, order_id, store_name, remarks, order_id, store_name, order_id, store_name)
            affected = 0
            while True:
                if cur.rowcount > 0:
                    affected += cur.rowcount
                if not cur.nextset():
                    break
            conn.commit()
            return {"store_name": store_name, "order_id": order_id, "affected_rows": affected}
        except Exception:
            conn.rollback()
            raise


def previous_order_suppliers(store_name, order_id):
    """Port Form1.LoadDistinctOrSuppliers for the selected backup order."""
    sql = """
        SELECT OrSupplierCode, OrSupplier, COUNT(ProductCode) AS ProductCount
        FROM OrderManagementBackup
        WHERE StoreName = ? AND OrderId = ?
          AND ISNULL(LTRIM(RTRIM(OrSupplier)), '') <> ''
          AND ISNULL(LTRIM(RTRIM(OrSupplierCode)), '') <> ''
        GROUP BY OrSupplier, OrSupplierCode
        ORDER BY OrSupplier
    """
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(sql, store_name, order_id).fetchall()
        return [
            {
                "supplier_code": str(row.OrSupplierCode),
                "supplier_name": row.OrSupplier,
                "product_count": int(row.ProductCount),
            }
            for row in rows
        ]


def previous_order_supplier_products(store_name, order_id, supplier_code):
    """Review rows shown by Form1.DGVMapping_SelectionChanged before compare."""
    sql = """
        SELECT o.ProductCode AS CurrentProductCode, o.ProductName AS CurrentProductName,
               o.OrderQty AS CurrentOrderQty, o.WantedType AS CurrentWantedType,
               b.ProductCode AS PreviousProductCode, b.ProductName AS PreviousProductName,
               b.OrQty AS PreviousOrderedQty, b.TotalStock AS PreviousStock,
               o.TotalStock AS CurrentStock, b.Remarks AS PreviousRemarks,
               b.Status AS PreviousStatus
        FROM OrderManagementBackup b
        LEFT JOIN OrderManagement o
          ON b.ProductCode = o.ProductCode AND o.StoreName = b.StoreName
        WHERE b.StoreName = ? AND b.OrderId = ? AND b.OrSupplierCode = ?
        ORDER BY COALESCE(o.ProductName, b.ProductName)
    """
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name, order_id, supplier_code)
        columns = [column[0] for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def compare_previous_order_supplier(store_name, order_id, supplier_code):
    """Port Form1.CompareOrderManagementSupplierWise atomically."""
    sql = """
    UPDATE om SET om.OrQty = omb.OrQty, om.OrSupplier = omb.OrSupplier,
        om.Status = 2, om.Remarks = ?
    FROM OrderManagement om
    INNER JOIN OrderManagementBackup omb ON om.ProductCode = omb.ProductCode
    WHERE omb.OrderId = ? AND (omb.Status = 1 OR omb.Status = 0)
      AND om.StoreName = ? AND omb.OrSupplierCode = ?
      AND ((omb.TotalStock > om.TotalStock AND om.StoreName = omb.StoreName)
           OR (omb.Status = 1 OR omb.OrderQty = 0));

    UPDATE om SET om.OrderQty = (om.OrgOrderQty - omb.OrQty), om.Status = 0,
        om.Remarks = 'After Order Sold', om.WantedType = 'After Order Sold'
    FROM OrderManagement om
    INNER JOIN OrderManagementBackup omb ON om.ProductCode = omb.ProductCode
    WHERE omb.OrderId = ? AND om.StoreName = ? AND omb.OrSupplierCode = ?
      AND omb.TotalStock > om.TotalStock AND om.StoreName = omb.StoreName
      AND (om.OrderQty - omb.OrQty) > 0;
    """
    remarks = f"Compare Supplier {supplier_code} with Order ID: {order_id}"
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                sql,
                remarks, order_id, store_name, supplier_code,
                order_id, store_name, supplier_code,
            )
            affected = 0
            while True:
                if cur.rowcount > 0:
                    affected += cur.rowcount
                if not cur.nextset():
                    break
            conn.commit()
            return {
                "store_name": store_name,
                "order_id": order_id,
                "supplier_code": supplier_code,
                "affected_rows": affected,
            }
        except Exception:
            conn.rollback()
            raise
