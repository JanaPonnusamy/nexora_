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
    p.SubLocation,
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
                "rack": (r.SubLocation or "").strip() or None,
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
        # This replace is a delete+reinsert, so a row's previous Rack would
        # otherwise be lost outright whenever the source has no SubLocation
        # for that cycle. Carry the last known Rack forward per product so a
        # blank source value doesn't wipe a rack that was already on file.
        existing_racks = {
            str(r.supplierproductcode): r.Rack
            for r in cur.execute(
                "SELECT supplierproductcode, Rack FROM SupplierStock "
                "WHERE storename = ? AND suppliercode = ?",
                (target_store_name, supplier_code),
            ).fetchall()
            if r.Rack
        }
        cur.execute(
            "DELETE FROM SupplierStock WHERE storename = ? AND suppliercode = ?",
            (target_store_name, supplier_code),
        )
        if rows:
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO SupplierStock "
                "(suppliercode, supplierproductcode, supplierproductname, mrp, ptr, "
                "stock, discound, packing, storename, sch, free, transactiondate, minqty, Rack) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?)",
                [
                    (supplier_code, r["code"], r["name"], None, None,
                     r["stock"], str(r["disc_percent"]), None, target_store_name, 0, 0, None,
                     r.get("rack") or existing_racks.get(str(r["code"])))
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


def update_order_qty(store_name, product_code, order_qty):
    """Manual review edit to the live grid (Form1's editable OrderQty cell).

    Setting order_qty = 0 is how a user marks a product "no need" -- it stays
    Status 0 here but is what compare_previous_order's OrderQty = 0 rule looks
    for on the next cycle to close the row out without a supplier order.
    """
    sql = (
        "UPDATE OrderManagement SET OrderQty = ?, Remarks = CASE WHEN ? = 0 "
        "THEN 'No Need - Reviewed' ELSE Remarks END "
        "WHERE StoreName = ? AND ProductCode = ?"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, order_qty, order_qty, store_name, product_code)
        updated = cur.rowcount
        conn.commit()
        return updated


def qty_check_rows(store_name):
    """Port of Form1.GetQtyCheckQuery('All', 'All') -- the Qty Check screen's
    main grid: only rows not yet reviewed (qtycheck = 0, status = 0)."""
    sql = (
        "SELECT productcode, productname, orderqty, totalstock, saleunit, unitdescription, "
        "slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty, Transactiondate, wantedtype "
        "FROM ordermanagement WHERE qtycheck = 0 AND status = 0 AND storename = ? "
        "ORDER BY productname"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_qty_check(store_name, product_code, order_qty):
    """Port of dgvMain_CellEndEdit -> UpdateDatabase(productCode, newQty, remark)
    -> UpdateValues. The remark mirrors the VB diff message; qtycheck flips to
    1 so the row drops off the Qty Check grid the moment it's reviewed --
    whether zeroed (Escape, "Don't Want to Order") or committed with a value
    (Enter)."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT orderqty FROM ordermanagement WHERE productcode = ? AND storename = ? AND status = 0",
            product_code, store_name,
        ).fetchone()
        if not row:
            return None
        old_qty = int(row[0]) if row[0] is not None else 0
        diff = order_qty - old_qty
        if order_qty == 0:
            remark = "Don't Want to Order"
        elif diff == 0:
            remark = "No Changes in OrderQty"
        elif diff > 0:
            remark = f"OrderQty Changed {diff} Add"
        else:
            remark = f"OrderQty Changed {abs(diff)} Less"

        cur.execute(
            "UPDATE ordermanagement SET orderqty = ?, remarks = ?, qtycheck = 1 "
            "WHERE productcode = ? AND storename = ? AND status = 0",
            order_qty, remark, product_code, store_name,
        )
        conn.commit()
        return {"order_qty": order_qty, "remarks": remark}


def qty_check_purchase_details(store, product_code, mode):
    """Port of RetrieveDataForPurchaseDetailsAsync -- last 10 GRN/purchase
    lines for a product, from PurchaseTrans on either the central OrderNMC
    copy (mode='local') or the live branch DB (mode='remote')."""
    is_local = mode != "remote"
    supplier_table = "OrderSuppliers" if is_local else "Suppliers"
    supplier_store_filter = " AND sup.StoreName = ?" if is_local else ""
    store_filter = " AND pt.StoreName = ?" if is_local else ""

    sql = (
        "SELECT TOP 10 pt.StockReceived AS RStock, pt.FreeQty, "
        "pt.ProductDiscPercent AS DIS, pt.ItemCost, pt.PurchasePrice AS PTR, "
        "pt.MRP, pt.GRNDate, "
        "CASE WHEN pt.InvoiceSeries = 'TI' THEN src.StoreName ELSE sup.SupplierName END AS SupplierName "
        f"FROM PurchaseTrans pt WITH (NOLOCK) "
        f"LEFT JOIN {supplier_table} sup WITH (NOLOCK) "
        f"ON pt.InvoiceSeries <> 'TI' AND pt.SupplierCode = sup.SupplierCode{supplier_store_filter} "
        "OUTER APPLY ("
        "  SELECT TOP 1 s.StoreName FROM Stores s WITH (NOLOCK) "
        "  WHERE pt.InvoiceSeries = 'TI' AND CAST(s.StoreCode AS varchar(50)) = pt.SupplierCode"
        ") src "
        f"WHERE pt.ProductCode = ?{store_filter} "
        "ORDER BY pt.GRNDate DESC"
    )
    params = []
    if is_local:
        params.append(store["store_name"])
    params.append(product_code)
    if is_local:
        params.append(store["store_name"])

    conn = database.get_central_connection() if is_local else database.get_branch_connection(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    with conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def qty_check_sales_details(store, product_code, mode):
    """Port of RetrieveDataForSalesDetailsAsync -- last 10 sale lines for a
    product, from ProductSaleInformation/SaleInformation/SalesRep."""
    is_local = mode != "remote"
    store_filter = " AND {alias}.StoreName = ?"

    sql = (
        "SELECT TOP 10 SUM(PS.quantity) AS TotalQuantity, s.Billtime AS Bill_Time, "
        "sr.Salesmanname, s.CUSTOMERNAME, PS.DiscountPercentage AS dis, "
        "PS.Seriesname AS type, PS.mrp, PS.purchaseprice AS ptr, PS.Bnumber "
        "FROM ProductSaleInformation PS "
        "INNER JOIN saleinformation s ON PS.BillNumber = s.BillNumber AND PS.TransactionDate = s.BillDate"
        + (store_filter.format(alias="s") if is_local else "") + " "
        "INNER JOIN SalesRep sr ON s.DeliverySalesRep = sr.Salesmancode"
        + (store_filter.format(alias="sr") if is_local else "") + " "
        "WHERE PS.ProductCode = ? AND PS.TransactionValidity = 0"
        + (store_filter.format(alias="PS") if is_local else "") + " "
        "GROUP BY PS.Bnumber, s.BillTime, s.CUSTOMERNAME, PS.Seriesname, PS.mrp, "
        "PS.purchaseprice, PS.Lastadjustmentdate, PS.DiscountPercentage, sr.Salesmanname "
        "ORDER BY s.BillTime DESC"
    )
    params = []
    if is_local:
        params.append(store["store_name"])
    if is_local:
        params.append(store["store_name"])
    params.append(product_code)
    if is_local:
        params.append(store["store_name"])

    conn = database.get_central_connection() if is_local else database.get_branch_connection(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    with conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def qty_check_monthly_stats(store, product_code, mode):
    """Port of RetrieveDataForChartAsync -- last 3 months of ProductTrans
    stats, the source for the "Monthly Statistics" chart."""
    is_local = mode != "remote"
    store_filter = " AND pt.StoreName = ?" if is_local else ""

    sql = (
        "SELECT pt.ProductCode, CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120) AS MonthOfStatistics, "
        "ISNULL(pt.SaleQuantity, 0) AS SaleQuantity, ISNULL(pt.StockInHand, 0) AS StockInHand, "
        "ISNULL(pt.PurchaseQuantity, 0) AS PurchaseQuantity, "
        "ISNULL(pt.AdjustmentQuantity, 0) AS AdjustmentQuantity, "
        "ISNULL(pt.TransferInQuantity, 0) AS TransferInQuantity, "
        "ISNULL(pt.TransferOutQuantity, 0) AS TransferOutQuantity "
        "FROM ProductTrans pt WITH (NOLOCK) "
        "WHERE pt.ProductCode = ? "
        "AND pt.MonthOfStatistics >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 3, 0)"
        f"{store_filter} "
        "ORDER BY pt.MonthOfStatistics ASC"
    )
    params = [product_code]
    if is_local:
        params.append(store["store_name"])

    conn = database.get_central_connection() if is_local else database.get_branch_connection(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    with conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def qty_check_order_history(store_name, product_code):
    """Port of RetrieveDataForOrderDetailsAsync -- last 25 OrderManagementBackup
    rows for this product, always from the central OrderNMC copy regardless
    of local/remote mode (matches the VB call site)."""
    sql = (
        "SELECT TOP 25 Productcode, ProductName, Orqty, OrgOrderQty, saleunit, MRP, "
        "remarks, Wanteddate, WantedType, Orsupplier "
        "FROM OrderManagementBackup WHERE Productcode = ? AND StoreName = ? "
        "ORDER BY Wanteddate DESC"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, product_code, store_name)
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
    """Port Form1.CompareOrderManagement's comparison rules atomically."""
    remarks = f"Compare Order with {order_id}"
    sql = """
    -- Rule 1: backup item was fully assigned (status=1) -> carry supplier + ordered
    -- qty forward and mark the current record processed.
    UPDATE om SET om.OrQty = omb.OrQty, om.OrSupplier = omb.OrSupplier,
        om.Status = 2, om.Remarks = ?
    FROM OrderManagement om INNER JOIN OrderManagementBackup omb
        ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
    WHERE omb.OrderId = ? AND omb.Status = 1 AND omb.OrSupplier IS NOT NULL
        AND omb.OrQty IS NOT NULL AND om.StoreName = ?;
    -- Rule 2: backup item still open (status=0) but a supplier and qty were chosen
    -- -> mark the current record processed (do not copy supplier/qty).
    UPDATE om SET om.Status = 2, om.Remarks = ?
    FROM OrderManagement om INNER JOIN OrderManagementBackup omb
        ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
    WHERE omb.OrderId = ? AND omb.Status = 0 AND om.StoreName = ?
        AND omb.OrSupplier IS NOT NULL AND omb.OrQty IS NOT NULL;
    -- Rule 3: user manually reviewed the item (qtycheck=1) and intentionally set
    -- OrderQty to 0. Item is considered processed: mark status=2 and the comparison
    -- remark only. Do NOT copy supplier, do NOT copy ordered qty, do NOT recalc demand.
    UPDATE om SET om.Status = 2, om.Remarks = ?
    FROM OrderManagement om INNER JOIN OrderManagementBackup omb
        ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
    WHERE omb.OrderId = ? AND omb.Status = 0 AND omb.QtyCheck = 1
        AND omb.OrderQty = 0 AND omb.Remarks IS NOT NULL AND om.StoreName = ?;
    -- Rule 4: stock sold since the backup -> reduce the outstanding qty and reopen.
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
            cur.execute(
                sql,
                remarks, order_id, store_name,
                remarks, order_id, store_name,
                remarks, order_id, store_name,
                order_id, store_name,
            )
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
