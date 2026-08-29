"""Reads from the legacy OrderNMC database."""
from modules.legacy_order import database


_WORKFLOW_SCHEMA_SQL = """
IF OBJECT_ID('dbo.LegacyOrderWorkflow', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyOrderWorkflow (
        WorkflowId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
        StoreName NVARCHAR(100) NOT NULL,
        OrderId BIGINT NOT NULL,
        Status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
        StartedAt DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
        FinalizedAt DATETIME2(0) NULL,
        UpdatedBy NVARCHAR(128) NULL,
        Note NVARCHAR(500) NULL,
        CONSTRAINT UQ_LegacyOrderWorkflow_Store_Order UNIQUE (StoreName, OrderId),
        CONSTRAINT CK_LegacyOrderWorkflow_Status CHECK (
            Status IN ('DRAFT', 'QTY_REVIEW', 'SUPPLIER_ASSIGNMENT', 'READY', 'FINALIZED')
        )
    );
END;
IF OBJECT_ID('dbo.LegacyOrderWorkflowAudit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LegacyOrderWorkflowAudit (
        AuditId BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        StoreName NVARCHAR(100) NOT NULL,
        OrderId BIGINT NOT NULL,
        ProductCode BIGINT NULL,
        Action VARCHAR(40) NOT NULL,
        OldValue NVARCHAR(500) NULL,
        NewValue NVARCHAR(500) NULL,
        Actor NVARCHAR(128) NULL,
        CreatedAt DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
"""


def _ensure_workflow_schema(cur):
    """Apply the additive workflow schema without changing legacy tables."""
    cur.execute(_WORKFLOW_SCHEMA_SQL)
    while cur.nextset():
        pass


def _latest_order_id(cur, store_name):
    row = cur.execute(
        "SELECT MAX(OrderId) FROM OrderManagement WHERE StoreName = ?", store_name
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _workflow_counts(cur, store_name, order_id):
    row = cur.execute(
        """
        SELECT COUNT(*) AS TotalLines,
               SUM(CASE WHEN Status = 0 AND QtyCheck = 0 THEN 1 ELSE 0 END) AS QtyPending,
               SUM(CASE WHEN Status = 0 AND QtyCheck = 1 THEN 1 ELSE 0 END) AS QtyReviewed,
               SUM(CASE WHEN Status = 1 AND OrderQty > 0 THEN 1 ELSE 0 END) AS AssignedLines,
               SUM(CASE WHEN Status = 0 AND OrderQty > 0 THEN 1 ELSE 0 END) AS UnassignedLines,
               SUM(CASE WHEN Status = 2 OR OrderQty = 0 THEN 1 ELSE 0 END) AS ClosedLines,
               SUM(CASE WHEN Status = 1 THEN ISNULL(OrQty, OrderQty) ELSE 0 END) AS AssignedQty,
               SUM(CASE WHEN Status = 1 THEN ISNULL(OrQty, OrderQty) * ISNULL(PurchasePrice, 0) ELSE 0 END) AS AssignedValue,
               COUNT(DISTINCT CASE WHEN Status = 1 THEN OrSupplierCode END) AS SupplierCount
        FROM OrderManagement WHERE StoreName = ? AND OrderId = ?
        """,
        store_name, order_id,
    ).fetchone()
    values = [0 if value is None else value for value in row]
    return {
        "total_lines": int(values[0]),
        "qty_pending": int(values[1]),
        "qty_reviewed": int(values[2]),
        "assigned_lines": int(values[3]),
        "unassigned_lines": int(values[4]),
        "closed_lines": int(values[5]),
        "assigned_qty": int(values[6]),
        "assigned_value": float(values[7]),
        "supplier_count": int(values[8]),
    }


def _record_line_audit(cur, store_name, order_id, product_code, action, old_value, new_value, actor):
    cur.execute(
        "INSERT dbo.LegacyOrderWorkflowAudit "
        "(StoreName, OrderId, ProductCode, Action, OldValue, NewValue, Actor) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        store_name, order_id, product_code, action,
        None if old_value is None else str(old_value),
        None if new_value is None else str(new_value), actor,
    )


def order_workflow_summary(store_name):
    """Current order readiness plus the durable finalization state."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        conn.commit()
        order_id = _latest_order_id(cur, store_name)
        if order_id is None:
            return {
                "store_name": store_name, "order_id": None, "status": "DRAFT",
                "ready": False, "total_lines": 0, "qty_pending": 0,
                "qty_reviewed": 0, "assigned_lines": 0, "unassigned_lines": 0,
                "closed_lines": 0, "assigned_qty": 0, "assigned_value": 0.0,
                "supplier_count": 0, "updated_at": None, "updated_by": None,
                "finalized_at": None, "note": None,
            }
        counts = _workflow_counts(cur, store_name, order_id)
        state = cur.execute(
            "SELECT Status, UpdatedAt, UpdatedBy, FinalizedAt, Note "
            "FROM dbo.LegacyOrderWorkflow WHERE StoreName = ? AND OrderId = ?",
            store_name, order_id,
        ).fetchone()
        ready = counts["total_lines"] > 0 and counts["qty_pending"] == 0 and counts["unassigned_lines"] == 0
        if state and state.Status == "FINALIZED":
            status = "FINALIZED"
        elif counts["qty_pending"] > 0:
            status = "QTY_REVIEW"
        elif counts["unassigned_lines"] > 0:
            status = "SUPPLIER_ASSIGNMENT"
        elif ready:
            status = "READY"
        else:
            status = "DRAFT"
        return {
            "store_name": store_name, "order_id": order_id, "status": status,
            "ready": ready, **counts,
            "updated_at": state.UpdatedAt if state else None,
            "updated_by": state.UpdatedBy if state else None,
            "finalized_at": state.FinalizedAt if state else None,
            "note": state.Note if state else None,
        }


def set_order_workflow_finalized(store_name, actor, note=None, reopen=False):
    """Finalize or reopen the latest order without changing legacy line semantics."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        order_id = _latest_order_id(cur, store_name)
        if order_id is None:
            raise ValueError("No generated order exists for this store.")
        counts = _workflow_counts(cur, store_name, order_id)
        ready = counts["total_lines"] > 0 and counts["qty_pending"] == 0 and counts["unassigned_lines"] == 0
        if not reopen and not ready:
            raise ValueError(
                f"Order is not ready: {counts['qty_pending']} quantity checks and "
                f"{counts['unassigned_lines']} supplier assignments remain."
            )
        status = "READY" if reopen else "FINALIZED"
        finalized_at = None if reopen else "SYSUTCDATETIME()"
        cur.execute(
            f"""
            MERGE dbo.LegacyOrderWorkflow AS target
            USING (SELECT ? AS StoreName, ? AS OrderId) AS source
              ON target.StoreName = source.StoreName AND target.OrderId = source.OrderId
            WHEN MATCHED THEN UPDATE SET Status = ?, UpdatedAt = SYSUTCDATETIME(),
                UpdatedBy = ?, Note = ?, FinalizedAt = {finalized_at if finalized_at else 'NULL'}
            WHEN NOT MATCHED THEN INSERT
                (StoreName, OrderId, Status, UpdatedBy, Note, FinalizedAt)
                VALUES (?, ?, ?, ?, ?, {finalized_at if finalized_at else 'NULL'});
            """,
            store_name, order_id, status, actor, note,
            store_name, order_id, status, actor, note,
        )
        cur.execute(
            "INSERT dbo.LegacyOrderWorkflowAudit "
            "(StoreName, OrderId, Action, NewValue, Actor) VALUES (?, ?, ?, ?, ?)",
            store_name, order_id, "ORDER_REOPENED" if reopen else "ORDER_FINALIZED",
            note, actor,
        )
        conn.commit()
    return order_workflow_summary(store_name)


def order_workflow_audit(store_name, limit=50):
    limit = max(1, min(int(limit), 200))
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        conn.commit()
        order_id = _latest_order_id(cur, store_name)
        if order_id is None:
            return []
        cur.execute(
            f"SELECT TOP {limit} AuditId, OrderId, ProductCode, Action, OldValue, "
            "NewValue, Actor, CreatedAt FROM dbo.LegacyOrderWorkflowAudit "
            "WHERE StoreName = ? AND OrderId = ? ORDER BY CreatedAt DESC, AuditId DESC",
            store_name, order_id,
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


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
        "LastSaleDate, LastReceivedDate, WantedDate, Status, Remarks, "
        "OrSupplier, OrSupplierCode "
        "FROM OrderManagement WHERE StoreName = ? ORDER BY ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_order_qty(store_name, product_code, order_qty, actor=None):
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
        _ensure_workflow_schema(cur)
        row = cur.execute(
            "SELECT OrderId, OrderQty FROM OrderManagement WHERE StoreName = ? AND ProductCode = ?",
            store_name, product_code,
        ).fetchone()
        if not row:
            return 0
        cur.execute(sql, order_qty, order_qty, store_name, product_code)
        updated = cur.rowcount
        if updated:
            _record_line_audit(
                cur, store_name, int(row.OrderId), product_code, "ORDER_QTY_CHANGED",
                row.OrderQty, order_qty, actor,
            )
        conn.commit()
        return updated


# --------------------------------------------------------------------------
# Supplier-assignment ordering workflow -- the VB dgvMain grid driven by the
# dgvSupplierList search. A user picks a supplier, sees that supplier's
# orderable OrderManagement rows (by purchase history OR by live supplier
# stock), then assigns the supplier + the line's qty to each product.
# --------------------------------------------------------------------------

def list_suppliers(store_name, search=""):
    """Port of Form1.txtSupplierSearch_TextChanged -- the supplier search list
    (dgvSupplierList). UnifiedSupplierCODE may be a comma-joined set of the
    branch's real SupplierCodes, which is why the by-supplier filters split it."""
    sql = (
        "SELECT UnifiedSupplierCODE, SupplierNAME FROM OrderSuppliers "
        "WHERE SupplierNAME LIKE ? AND storename = ? ORDER BY SupplierNAME"
    )
    like = f"{(search or '').strip()}%"
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(sql, like, store_name).fetchall()
        return [
            {"supplier_code": str(r.UnifiedSupplierCODE), "supplier_name": r.SupplierNAME}
            for r in rows
        ]


# Common OrderManagement projection for the workspace grid, PascalCase so the
# rows are structurally compatible with the Review-All order_summary rows.
_WORKSPACE_COLS = (
    "om.ProductCode, om.ProductName, om.OrderQty, om.TotalStock, om.SLSQty, "
    "om.UnitDescription, om.SaleUnit, om.MRP, om.WantedType, om.Remarks, "
    "om.PurchasePrice, om.SubLocation, om.ProductTypeName, om.MaxQty, om.Status"
)


def orders_by_supplier(store_name, supplier_code, mode):
    """mode='history' ports LoadDataForSupplier (products this supplier has
    historically supplied, via OrderPurchaseTrans); mode='stock' ports
    LoadDataForSupplierStock (products matched to the supplier's live
    SupplierStock, with per-supplier stock/rack columns). Both only show
    still-open rows (status=0, orderqty>0)."""
    if mode == "stock":
        sql = (
            "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.TotalStock, "
            "om.SLSQty, om.UnitDescription, om.SaleUnit, om.MRP, om.WantedType, "
            "om.Remarks, om.PurchasePrice, om.SubLocation, om.ProductTypeName, "
            "om.MaxQty, om.Status, "
            "SS.Stock AS S_Stock, SS.discound AS Discount, SS.MINQTY AS MinQty, "
            "SS.sch AS Sch, SS.free AS Free, SS.SupplierProductName, "
            "SS.SupplierProductCode, ISNULL(SS.Rack, '') AS Rack "
            "FROM OrderManagement om "
            "INNER JOIN SupplierProductMatch SPM "
            "  ON om.ProductCode = SPM.ProductCode AND SPM.StoreName = om.StoreName "
            "  AND SPM.SupplierCode = ? "
            "INNER JOIN SupplierStock SS "
            "  ON SS.SupplierProductCode = SPM.SupplierProductCode "
            "  AND SS.SupplierCode = ? AND SS.storename = ? "
            "WHERE om.storename = ? AND om.status = 0 AND om.orderqty > 0 AND SS.Stock > 0 "
            "ORDER BY om.ProductName"
        )
        params = (supplier_code, supplier_code, store_name, store_name)
    else:
        # EXISTS (not a JOIN) so a product with several historical purchase
        # lines from this supplier still shows exactly once.
        sql = (
            f"SELECT {_WORKSPACE_COLS} FROM OrderManagement om "
            "WHERE om.Status = 0 AND om.OrderQty > 0 "
            "AND om.ProductTypeName IN ('Pharma', 'Non Pharma') AND om.StoreName = ? "
            "AND EXISTS (SELECT 1 FROM OrderPurchaseTrans op "
            "  WHERE op.ProductCode = om.ProductCode AND op.StoreName = om.StoreName "
            "  AND op.SupplierCode IN (SELECT Value FROM dbo.SplitString(?, ','))) "
            "ORDER BY om.ProductTypeName, om.ProductName"
        )
        params = (store_name, supplier_code)

    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def assigned_orders(store_name, supplier_code):
    """Port of Form1.FetchSupplierOrderDetails -- rows already assigned to this
    supplier (status=1)."""
    sql = (
        "SELECT ProductCode, ProductName, OrderQty, SaleUnit, MRP, OrSupplier, "
        "Remarks, PurchasePrice, TotalStock, WantedType, Status "
        "FROM OrderManagement "
        "WHERE status = 1 AND orderqty > 0 AND storename = ? "
        "AND orsuppliercode IN (SELECT Value FROM dbo.SplitString(?, ',')) "
        "ORDER BY ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name, supplier_code)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def assign_supplier(store_name, product_code, supplier_code, supplier_name, actor=None):
    """Port of Form1.UpdateDatabase(productCode) -- the status 0<->1 assign
    toggle. Assigning copies the line's current OrderQty into OrQty and stamps
    the supplier (status 1). Toggling an assigned row clears supplier + OrQty
    back to status 0. Rows already closed by Compare (status 2) are left alone.
    Returns None if the product isn't in this store's OrderManagement."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        row = cur.execute(
            "SELECT status, orderqty, OrderId, OrSupplierCode FROM ordermanagement "
            "WHERE productcode = ? AND storename = ?",
            product_code, store_name,
        ).fetchone()
        if not row:
            return None
        status = int(row[0]) if row[0] is not None else 0
        if status == 0:
            orqty = int(row[1]) if row[1] is not None else 0
            cur.execute(
                "UPDATE ordermanagement SET orqty = ?, orsupplier = ?, "
                "orsuppliercode = ?, status = 1 "
                "WHERE productcode = ? AND status = 0 AND storename = ?",
                orqty, supplier_name, supplier_code, product_code, store_name,
            )
            _record_line_audit(
                cur, store_name, int(row.OrderId), product_code, "SUPPLIER_ASSIGNED",
                row.OrSupplierCode, supplier_code, actor,
            )
            conn.commit()
            return {"product_code": product_code, "status": 1, "order_qty": orqty, "changed": True}
        if status == 1:
            cur.execute(
                "UPDATE ordermanagement SET orqty = NULL, orsupplier = NULL, "
                "orsuppliercode = NULL, status = 0 "
                "WHERE productcode = ? AND status = 1 AND storename = ?",
                product_code, store_name,
            )
            _record_line_audit(
                cur, store_name, int(row.OrderId), product_code, "SUPPLIER_UNASSIGNED",
                row.OrSupplierCode, None, actor,
            )
            conn.commit()
            return {"product_code": product_code, "status": 0, "order_qty": None, "changed": True}
        # status 2 (already processed by a previous-order compare) -- untouched.
        return {"product_code": product_code, "status": status, "order_qty": row[1], "changed": False}


def qty_check_rows(store_name):
    """Port of Form1.GetQtyCheckQuery('All', 'All') -- the Qty Check screen's
    main grid: only rows not yet reviewed (qtycheck = 0, status = 0)."""
    sql = (
        "SELECT productcode, productname, orderqty, totalstock, saleunit, unitdescription, "
        "slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty, Transactiondate, wantedtype, "
        "producttypename "
        "FROM ordermanagement WHERE qtycheck = 0 AND status = 0 AND storename = ? "
        "ORDER BY productname"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_qty_check(store_name, product_code, order_qty, actor=None):
    """Port of dgvMain_CellEndEdit -> UpdateDatabase(productCode, newQty, remark)
    -> UpdateValues. The remark mirrors the VB diff message; qtycheck flips to
    1 so the row drops off the Qty Check grid the moment it's reviewed --
    whether zeroed (Escape, "Don't Want to Order") or committed with a value
    (Enter)."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        row = cur.execute(
            "SELECT orderqty, OrderId FROM ordermanagement "
            "WHERE productcode = ? AND storename = ? AND status = 0",
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
        _record_line_audit(
            cur, store_name, int(row.OrderId), product_code, "QTY_REVIEWED",
            old_qty, order_qty, actor,
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
