"""Reads from the legacy OrderNMC database."""
import datetime
import os
import re

from modules.legacy_order import database
from modules.product_mapping import repository as product_mapping_repository


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


class NoCurrentDateOrder(RuntimeError):
    """Raised by current_date_order when the store's latest order either does
    not exist, or exists but was not generated today -- i.e. there is no
    unambiguous "today's order" to validate pending rows against. Callers
    must stop and report rather than guess (e.g. falling back to whatever
    MAX(OrderId) happens to be, which could be a stale, already-reviewed
    order from a previous day that was simply never regenerated)."""
    def __init__(self, store_name, reason):
        self.store_name = store_name
        self.reason = reason
        super().__init__(f"'{store_name}': {reason}")


def current_date_order(cur, store_name):
    """Resolve "the current-date order" for a store, proven rather than
    assumed.

    OrderId is NOT a sequence -- it is a per-second timestamp string stamped
    onto every row a single order_process run produces (see sql/order_local.
    sql: CONVERT(VARCHAR(8), GETDATE(), 112) + HH + MM + SS). MAX(OrderId) is
    therefore "the most recently generated order", which is only the SAME
    thing as "today's order" if that run actually happened today -- an
    untouched store whose last run was yesterday (or longer ago) would
    otherwise have its stale order silently treated as current.

    This is checked two independent ways against the SAME row, both must
    agree:
      1. the OrderId's own leading 8 characters (YYYYMMDD, the date portion
         VB/this port stamps it with) equal today's date, and
      2. WantedDate (the business date column, set to GETDATE() at the same
         generation moment -- see order_process.COLUMN_MAP) falls on the
         same calendar day.
    "Today" is read from the DATABASE server's clock (GETDATE()), not the
    application host's, so this can't drift from whatever server actually
    time-stamped the rows.

    Returns the int OrderId if both checks agree it is today's. Raises
    NoCurrentDateOrder if there is no order at all, or the latest one is not
    from today, or the two date signals disagree with each other (a torn/
    unexpected row the caller should not silently act on).
    """
    row = cur.execute(
        """
        SELECT MAX(OrderId) AS LatestOrderId,
               CONVERT(VARCHAR(8), GETDATE(), 112) AS TodayStamp
        FROM OrderManagement WHERE StoreName = ?
        """,
        store_name,
    ).fetchone()
    latest_order_id = row.LatestOrderId if row else None
    if latest_order_id is None:
        raise NoCurrentDateOrder(store_name, "no order has been generated for this store yet.")
    today_stamp = row.TodayStamp
    order_id_str = str(int(latest_order_id))
    order_id_date = order_id_str[:8] if len(order_id_str) >= 8 else None

    wanted_row = cur.execute(
        "SELECT TOP 1 CONVERT(VARCHAR(8), WantedDate, 112) AS WantedStamp "
        "FROM OrderManagement WHERE StoreName = ? AND OrderId = ?",
        store_name, latest_order_id,
    ).fetchone()
    wanted_stamp = wanted_row.WantedStamp if wanted_row and wanted_row.WantedStamp else None

    if order_id_date != today_stamp:
        raise NoCurrentDateOrder(
            store_name,
            f"the latest order (#{latest_order_id}) was generated on "
            f"{order_id_date}, not today ({today_stamp}). Refusing to treat "
            "it as the current-date order.",
        )
    if wanted_stamp is not None and wanted_stamp != today_stamp:
        raise NoCurrentDateOrder(
            store_name,
            f"the latest order (#{latest_order_id})'s OrderId date "
            f"({order_id_date}) and WantedDate ({wanted_stamp}) disagree -- "
            "cannot unambiguously identify today's order.",
        )
    return int(latest_order_id)


def require_current_date_order_if_any(store_name):
    """Own-connection wrapper around current_date_order for callers (service.
    start_order_process) that just need the pre-flight validation, same
    pattern as qty_check_confirmation_count -- a single mockable repository
    call rather than the caller opening its own connection inline.

    A store with no order yet is fine (nothing to validate) -- only raises
    NoCurrentDateOrder when an order EXISTS but is not provably today's."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        if _latest_order_id(cur, store_name) is None:
            return None
        return current_date_order(cur, store_name)


def _workflow_counts(cur, store_name, order_id):
    row = cur.execute(
        """
        SELECT COUNT(*) AS TotalLines,
               -- Or Qty 0 lines are "no need" (counted as closed below) and are
               -- not listed on the Qty Check grid, so they never block Finalize.
               SUM(CASE WHEN Status = 0 AND QtyCheck = 0 AND OrderQty > 0 THEN 1 ELSE 0 END) AS QtyPending,
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


def record_protected_backup_snapshot(cur, store_name, order_id):
    """Pre-flight audit signal for the backup that insert_data_into_
    destination is about to take (see that function -- it unconditionally
    backs up EVERY row, every status, before every destructive rewrite, in
    the same transaction; this does not change what gets backed up).

    Counts rows for the CURRENT order that are both reviewed (QtyCheck = 1)
    and already assigned to a supplier (Status = 1) -- i.e. rows a user has
    both confirmed the quantity on AND handed to a supplier, the most
    "finished" state a line reaches before export. When more than one such
    row exists, this writes an explicit LegacyOrderWorkflowAudit entry
    naming the count, so there is a durable, queryable record that THIS
    run's backup snapshot is what protects that reviewed+assigned work --
    distinct from the generic "order regenerated" signal a new OrderId
    already implies. Returns the count (0 if order_id is None or no rows
    qualify)."""
    if order_id is None:
        return 0
    row = cur.execute(
        "SELECT COUNT(*) FROM OrderManagement "
        "WHERE StoreName = ? AND OrderId = ? AND QtyCheck = 1 AND Status = 1",
        store_name, order_id,
    ).fetchone()
    count = int(row[0]) if row and row[0] is not None else 0
    if count > 1:
        _record_line_audit(
            cur, store_name, order_id, None, "PROTECTED_BACKUP_SNAPSHOT",
            None, f"{count} reviewed+assigned line(s) protected by this run's backup.", None,
        )
    return count


_LOCK_APPLOCK_PREFIX = "LegacyOrderProcessingLock:"


def _with_store_applock(cur, store_name):
    """Serialize the whole check-then-write critical section for this store
    across concurrent connections/transactions.

    Plain READ COMMITTED locking does NOT make the existing SELECT-then-MERGE
    sequence atomic: a SELECT finding no row takes no lock on that absence
    (there is no range/gap lock outside SERIALIZABLE), so two concurrent
    callers can both read 'no active lock' before either commits, then both
    reach the MERGE. MERGE's own MATCHED/NOT MATCHED decision is evaluated
    against that same unprotected read, so the second writer can either block
    and still attempt the INSERT branch (raising a PK violation on
    StoreName), or -- depending on the query plan -- succeed silently with a
    stale decision. sp_getapplock, scoped to one transaction (@LockOwner =
    'Transaction', auto-released on commit/rollback), closes that gap by
    making the second caller block until the first transaction ends, so it
    always re-observes the first caller's committed state rather than racing
    its read. HOLDLOCK/UPDLOCK on the SELECT would also work for this
    single-row target, but the app lock composes more simply with the extra
    OrderManagement read already inside this same critical section."""
    cur.execute(
        "DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
        "@LockOwner = 'Transaction', @LockTimeout = 10000; IF @r < 0 "
        "RAISERROR('Could not acquire the processing lock for %s (timeout or deadlock).', 16, 1, ?);",
        f"{_LOCK_APPLOCK_PREFIX}{store_name}", store_name,
    )
    while cur.nextset():
        pass


def pending_export_count_on_connection(cur, store_name):
    """Count of Status = 0 (not yet assigned to a supplier, so never
    exported -- see order_export.export_order, which assigns Status 0->1
    and exports in the same call) rows on the CURRENT order, on a cursor the
    caller already owns.

    This is a WARNING signal, not a lock: it is never persisted anywhere, so
    there is nothing here for an administrator to "unlock" -- the business
    rule this replaces (a permanent dbo.LegacyOrderProcessingLock row
    blocking every future Process attempt until explicitly unlocked) was
    removed because pending Status = 0 lines are routine mid-review state,
    not evidence of a problem. Returns (order_id, count); (None, 0) if no
    order exists yet."""
    order_id = _latest_order_id(cur, store_name)
    if order_id is None:
        return None, 0
    row = cur.execute(
        "SELECT COUNT(*) FROM OrderManagement WHERE StoreName = ? AND OrderId = ? AND Status = 0",
        store_name, order_id,
    ).fetchone()
    return order_id, int(row[0]) if row and row[0] is not None else 0


class PendingExportBlocked(RuntimeError):
    """Raised by require_no_pending_export_on_connection -- used ONLY by the
    restore-by-OrderId workflow (restore_backup_order), which keeps a hard,
    non-overridable block on pending Status = 0 lines: restoring backup data
    overwrites the CURRENT live rows by ProductCode match, which is exactly
    the data an in-flight qty-check edit on a pending line risks losing.
    Order Process itself no longer uses this -- it regenerates the whole
    order from scratch regardless of what was pending, so pending lines
    there are expected noise (see service.start_order_process's warn+admin-
    override gate), not a restore-style clobber risk."""
    def __init__(self, store_name, order_id, count):
        self.store_name = store_name
        self.order_id = order_id
        self.count = count
        super().__init__(
            f"'{store_name}' order #{order_id} has {count} line(s) pending export "
            "(Status = 0) -- restoring over them could discard in-progress review. "
            "Export or clear them first."
        )


def require_no_pending_export_on_connection(cur, store_name):
    """Hard block for restore_backup_order: raises PendingExportBlocked if
    the CURRENT order has any Status = 0 lines. Takes the same per-store
    applock as the short-lived Order Process concurrency guard (requirement:
    keep a short-lived lock preventing two simultaneous runs for the same
    store), so this also serializes against a concurrent Process run on this
    connection's transaction -- but, unlike the removed business lock, never
    persists anything, so there is no separate "unlock" action; the caller
    simply retries once the pending lines are actually gone."""
    _with_store_applock(cur, store_name)
    order_id, count = pending_export_count_on_connection(cur, store_name)
    if order_id is not None and count > 0:
        raise PendingExportBlocked(store_name, order_id, count)


def qty_check_confirmation_count(store_name):
    """Count of qty_check=1 AND status=0 rows for the store's latest order --
    the same scope as pending_order_rows, minus the Pharma/Non-Pharma filter
    (this count must reflect every row that screen can show, not a subset).
    Returns (order_id, count, sample) where sample is up to 10 product
    code/name pairs for the confirmation dialog. (None, 0, []) if no order
    has been generated yet."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        order_id = _latest_order_id(cur, store_name)
        if order_id is None:
            return None, 0, []
        rows = cur.execute(
            "SELECT productcode, productname FROM ordermanagement "
            "WHERE storename = ? AND orderid = ? AND qtycheck = 1 AND status = 0 "
            "ORDER BY productname",
            store_name, order_id,
        ).fetchall()
        sample = [{"product_code": int(r[0]), "product_name": r[1]} for r in rows[:10]]
        return order_id, len(rows), sample


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


def order_header_summary(store_name):
    """Latest OrderHeaderDetails row plus the current readiness fingerprint.

    Backs the Order Workspace footer (order number/date, last GRN, last C
    bill number/date) and the
    change-detection check on return-to-workspace: (order_id, updated_at)
    together are the cheapest trustworthy "has anything relevant changed"
    signal this schema has -- there is no revision/generation column, so an
    order regeneration is only visible as a new OrderId, and a line-level
    edit (qty/assignment) is only visible as a moved workflow UpdatedAt.

    LastGRN on OrderHeaderDetails is only the GRN NUMBER captured as a
    watermark at generation time (see update_order_header_details) -- it has
    no paired date column, so the GRN's own date/time is read fresh from
    PurchaseTrans here, same table/column (Grndate) that watermark read
    itself used, rather than reusing LastBillDateTime (that is the last SALE
    bill's timestamp, an unrelated watermark, and would mislabel the footer).
    """
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        conn.commit()
        order_id = _latest_order_id(cur, store_name)
        if order_id is None:
            return {
                "store_name": store_name, "order_id": None, "order_no": None,
                "order_datetime": None, "last_grn": None, "last_grn_datetime": None,
                "last_sale_bill_no": None, "last_bill_datetime": None,
                "updated_at": None,
            }
        header = cur.execute(
            "SELECT TOP 1 OrderNo, OrderDateTime, LastGRN, LastSaleBillNo, LastBillDateTime "
            "FROM OrderHeaderDetails WHERE StoreName = ? AND OrderId = ? "
            "ORDER BY OrderDateTime DESC",
            store_name, order_id,
        ).fetchone()
        last_grn = (header.LastGRN or None) if header else None
        last_grn_datetime = None
        if last_grn:
            grn_row = cur.execute(
                "SELECT TOP 1 Grndate FROM Purchasetrans "
                "WHERE StoreName = ? AND Grnnumber = ? ORDER BY Grndate DESC",
                store_name, last_grn,
            ).fetchone()
            if grn_row:
                last_grn_datetime = grn_row.Grndate
        state = cur.execute(
            "SELECT UpdatedAt FROM dbo.LegacyOrderWorkflow WHERE StoreName = ? AND OrderId = ?",
            store_name, order_id,
        ).fetchone()
        return {
            "store_name": store_name,
            "order_id": order_id,
            "order_no": header.OrderNo if header else None,
            "order_datetime": header.OrderDateTime if header else None,
            "last_grn": last_grn,
            "last_grn_datetime": last_grn_datetime,
            # Last "C" sale bill -- the other watermark UpdateOrderHeaderDetails
            # stamps alongside LastGRN (see order_process.py), captured here as-is
            # with no re-derivation (LastBillDateTime is already that bill's own
            # timestamp, unlike LastGRN which needed a join to get a date at all).
            "last_sale_bill_no": (header.LastSaleBillNo or None) if header else None,
            "last_bill_datetime": header.LastBillDateTime if header else None,
            "updated_at": state.UpdatedAt if state else None,
        }


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


STALE_SALE_BILL_MINUTES = 30


def last_sale_bill_age_minutes(store_name):
    """Minutes since this store's most recent synced sale bill (Billtime),
    or None if it has never synced a bill. Used to flag a sync that reports
    success but has stopped actually carrying fresh sale data."""
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT DATEDIFF(MINUTE, MAX(Billtime), GETDATE()) "
            "FROM SaleInformation WHERE StoreName = ?",
            store_name,
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def stale_sale_bill_warning(store_name):
    """Strong warning string when the last sale bill is stale/missing, else None."""
    age = last_sale_bill_age_minutes(store_name)
    if age is None:
        return (
            f"STRONG WARNING: '{store_name}' has no synced sale bill at all -- "
            "verify the branch is billing and the sync is actually reaching SaleInformation."
        )
    if age > STALE_SALE_BILL_MINUTES:
        return (
            f"STRONG WARNING: '{store_name}' has had no new sale bill in {age} minutes "
            f"(over the {STALE_SALE_BILL_MINUTES}-minute threshold) -- sync completed but "
            "billing data looks stale. Check the branch POS and the connection."
        )
    return None


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


def sync_supplier_product_match_from_mapping(store_name, supplier_code, source_store_code, rows):
    """Bridge this store's ProductCode to the source store's SupplierProductCode
    via dbo.product_mapping (NEVER raw ProductCode equality -- the two stores'
    catalogues are not guaranteed to share codes for the same drug) instead of
    the manual Supplier Excel Mapping flow real suppliers use (NMW isn't a
    real Excel-uploading supplier, so that table would otherwise stay empty
    for it forever, see start_stock_update).

    ``rows`` is the same list ``replace_supplier_stock`` was just given
    (source store's own branch_stock() rows) -- reused here so this doesn't
    re-fetch anything; only product_mapping lookups are new I/O.
    """
    store_id = database.platform_store_id(store_name)
    source_store_id = database.platform_store_id(source_store_code)
    if not store_id or not source_store_id:
        return 0
    tenant_id = database.platform_tenant_id(store_id)
    if not tenant_id:
        return 0

    # product_mapping rows are keyed by (source_store_id, source_product_code)
    # -> target_store_id/target_product_code. ``rows`` carries NMW's own
    # ProductCode (r["code"]), so NMW is the mapping's "source" here and this
    # store is the "target" -- the lookup direction is the reverse of how this
    # store's own ProductCode would normally be looked up. One bulk query for
    # the pair (was one connection per NMW product); it also accepts a PENDING
    # mapping whose target code equals NMW's -- e.g. NMC's "D MAG SPRAY 100ML
    # [VET]" sat PENDING on the name suffix alone, so NMW's stock never
    # reached NMC's order screen (see supplier_bridge_targets).
    targets = product_mapping_repository.supplier_bridge_targets(
        tenant_id, source_store_id, store_id,
    )
    matches = []
    for r in rows:
        target = targets.get(str(r["code"]).strip())
        if target:
            matches.append((target, str(r["code"]).strip()))

    if not matches:
        return 0

    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM SupplierProductMatch WHERE StoreName = ? AND SupplierCode = ?",
            (store_name, supplier_code),
        )
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO SupplierProductMatch (StoreName, SupplierCode, ProductCode, SupplierProductCode) "
            "VALUES (?, ?, ?, ?)",
            [(store_name, supplier_code, product_code, supplier_product_code)
             for product_code, supplier_product_code in matches],
        )
        conn.commit()
    return len(matches)


def order_summary(store_name):
    """Current OrderManagement rows for a store -- what the VB grid showed."""
    sql = (
        "SELECT om.OrderId, om.ProductCode, om.ProductName, om.TotalStock, om.SaleUnit, om.SLSQty, "
        "om.MinQty, om.MaxQty, om.OrderQty, om.OrgOrderQty, om.WantedType, om.ProductTypeName, "
        "om.Frequence, om.MRP, om.PurchasePrice, om.UnitDescription, om.SubLocation, "
        "om.LastSaleDate, om.LastReceivedDate, om.WantedDate, om.Status, om.Remarks, "
        "om.OrSupplier, om.OrSupplierCode, om.IsOffer "
        "FROM OrderManagement om WHERE om.StoreName = ? ORDER BY om.ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_remarks(store_name, product_code, remarks, actor=None):
    """Free-text remark the operator writes directly (e.g. the auto-filled
    "9+1" offer-pattern note) -- separate from the several OTHER places that
    incidentally stamp Remarks for their own specific marker text (no-need,
    compare-order, after-order-sold), none of which fit an arbitrary note."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        row = cur.execute(
            "SELECT OrderId, Remarks FROM OrderManagement WHERE StoreName = ? AND ProductCode = ?",
            store_name, product_code,
        ).fetchone()
        if not row:
            return None
        cur.execute(
            "UPDATE OrderManagement SET Remarks = ? WHERE StoreName = ? AND ProductCode = ?",
            remarks, store_name, product_code,
        )
        if row.OrderId is not None:
            _record_line_audit(
                cur, store_name, int(row.OrderId), product_code, "REMARKS_CHANGED",
                row.Remarks, remarks, actor,
            )
        conn.commit()
        return {"product_code": product_code, "remarks": remarks}


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
    branch's real SupplierCodes, which is why the by-supplier filters split it.

    Excludes only EXPLICITLY inactive suppliers. OrderSuppliers.IsActive is
    synced in from Suppliers/sync.Suppliers (sync_engine's Suppliers->
    OrderSuppliers projection -- see _ensure_supplier_isactive_column); it is
    NULL for any row not yet re-synced since that column was added, so
    treating NULL as "exclude" would wipe the picker for stores pending a
    resync; only a confirmed IsActive=0 counts as inactive. Since
    UnifiedSupplierCODE can be several real codes joined by commas,
    "excluded" means ALL of them are confirmed inactive (NOT EXISTS an
    active-or-unknown one), not just any single code among them."""
    sql = (
        "SELECT UnifiedSupplierCODE, SupplierNAME FROM OrderSuppliers os "
        "WHERE os.SupplierNAME LIKE ? AND os.storename = ? "
        "AND os.UnifiedSupplierCODE IS NOT NULL AND LTRIM(RTRIM(os.UnifiedSupplierCODE)) <> '' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM dbo.SplitString(os.UnifiedSupplierCODE, ',') ss "
        "  JOIN OrderSuppliers os2 ON os2.suppliercode = ss.Value AND os2.storename = os.storename "
        "  WHERE os2.IsActive = 0"
        ") "
        "ORDER BY os.SupplierNAME"
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
# Qtycheck is included so the By Supplier (history) grid can badge lines that
# haven't been reviewed yet in Qty Check.
_WORKSPACE_COLS = (
    "om.ProductCode, om.ProductName, om.OrderQty, om.OrgOrderQty, om.TotalStock, om.SLSQty, "
    "om.UnitDescription, om.SaleUnit, om.MRP, om.WantedType, om.Remarks, "
    "om.PurchasePrice, om.SubLocation, om.ProductTypeName, om.MaxQty, om.Status, "
    "om.Qtycheck"
)

# Main-grid offer indicator: has this product EVER (any supplier) had a
# free-qty offer in its real purchase history? Same non-'TI'-transfer,
# INT-cast-for-sargability pattern as orders_by_supplier's history EXISTS --
# deliberately not scoped to the currently selected supplier, so the mark is
# a general "this product sometimes comes with an offer" signal.
_OFFER_HISTORY_EXISTS = (
    "EXISTS (SELECT 1 FROM PurchaseTrans pt WITH (NOLOCK) "
    "WHERE pt.ProductCode = CAST(om.ProductCode AS INT) AND pt.StoreName = om.StoreName "
    "AND pt.InvoiceSeries <> 'TI' AND pt.FreeQty > 0)"
)

# Most recent GRN's received+free quantity, e.g. "9+1" -- used to auto-fill a
# Remarks note when the operator's entered Or Qty is a multiple of the base.
# A single supplier invoice's free-qty line is often SPLIT across multiple
# PurchaseTrans rows for the same product/GRN (confirmed live on NMS,
# 2026-10-17: 345 real cases, e.g. GRN 11783 product 9664 = row(5,0) +
# row(5,1), a genuine "10+1" deal that reading either row alone would
# misread as "5+1" or miss the free qty on) -- so this groups by Grnnumber
# and SUMs both columns per bill before picking the most recent one, rather
# than reading any single row's StockReceived/FreeQty directly.
_LAST_OFFER_PATTERN_APPLY = (
    "OUTER APPLY ("
    "  SELECT TOP 1 g.base_qty AS LastOfferBaseQty, g.free_qty AS LastOfferFreeQty"
    "  FROM ("
    "    SELECT pt.Grnnumber, SUM(pt.StockReceived) AS base_qty, SUM(pt.FreeQty) AS free_qty, MAX(pt.GRNDate) AS grn_date"
    "    FROM PurchaseTrans pt WITH (NOLOCK)"
    "    WHERE pt.ProductCode = CAST(om.ProductCode AS INT) AND pt.StoreName = om.StoreName AND pt.InvoiceSeries <> 'TI'"
    "    GROUP BY pt.Grnnumber"
    "    HAVING SUM(pt.FreeQty) > 0"
    "  ) g"
    "  ORDER BY g.grn_date DESC"
    ") lastoffer"
)


def _supplier_codes(supplier_code):
    """A picked supplier's code may be a UNIFIED set -- OrderSuppliers.
    UnifiedSupplierCODE comma-joins several real SupplierCodes (e.g. NMG's
    "107,109,108"). Returns the individual member codes."""
    return [c.strip() for c in str(supplier_code or "").split(",") if c.strip()]


def _assigned_code_values(supplier_code):
    """OrSupplierCode values that count as "assigned to this supplier". An
    assign stamps the code exactly as picked, so a unified supplier's lines
    carry the WHOLE "107,109,108" string -- matching only the split member
    codes (the old SplitString filter) never found them, which left Export
    with "no assigned products" and the Assigned view empty. Lines stamped
    with a single member code still match too."""
    full = str(supplier_code or "").strip()
    return [full] + [c for c in _supplier_codes(full) if c != full]


def _in_list(values):
    return ", ".join("?" for _ in values)


def _supplier_stock_apply(codes, apply_kind, in_stock_only):
    """Live-stock match for a (possibly unified) supplier: the best-stocked
    SupplierStock line across ALL member codes, one row per product -- a
    plain JOIN on several codes would duplicate a product every member
    carries. Params: the member codes, in order."""
    return (
        f"{apply_kind} (SELECT TOP 1 SS.Stock, SS.discound, SS.MINQTY, SS.sch, SS.free, "
        "  SS.SupplierProductName, SS.SupplierProductCode, SS.Rack "
        "  FROM SupplierProductMatch SPM "
        "  JOIN SupplierStock SS ON SS.SupplierProductCode = SPM.SupplierProductCode "
        "    AND SS.SupplierCode = SPM.SupplierCode AND SS.storename = om.StoreName "
        "  WHERE SPM.ProductCode = om.ProductCode AND SPM.StoreName = om.StoreName "
        f"    AND SPM.SupplierCode IN ({_in_list(codes)})"
        + (" AND SS.Stock > 0" if in_stock_only else "")
        + "  ORDER BY SS.Stock DESC) SS "
    )


def orders_by_supplier(store_name, supplier_code, mode):
    """mode='history' ports LoadDataForSupplier -- legacy's "Auto Pur UpDate"
    process (products this supplier has historically supplied); mode='stock'
    ports LoadDataForSupplierStock (products matched to the supplier's live
    SupplierStock, with per-supplier stock/rack columns). Both only show
    still-open rows (status=0, orderqty>0).

    An owner trial on 2026-10-13 briefly dropped this history restriction (to
    work around NMV having several "Purani" OrderSuppliers entries with
    different SupplierCodes/different history) and showed EVERY open product
    in the store regardless of supplier -- confirmed live as wrong (e.g.
    Colgate/Garnier general FMCG lines showing up under Purani), so the
    restriction is back. The multiple-codes-per-real-supplier gap is a
    separate, still-open problem -- picking the WRONG one of several
    same-named entries can legitimately show 0 history for a product the
    supplier does carry; that needs its own fix (e.g. merging duplicate
    OrderSuppliers rows), not removing this filter.

    mode='history' deliberately does NOT use OrderPurchaseTrans, unlike the
    legacy VB.NET query it ports (Form1.vb LoadDataForSupplier). That table is
    a legacy-only staging table with no equivalent freshness guarantee in this
    environment. PurchaseTrans is the real, actively-synced GRN/purchase-
    invoice table this module already sources purchase history from elsewhere
    (see qty_check_purchase_details) and from the store-scoping bug fix (see
    'TI transfer vs supplier collision' -- InvoiceSeries='TI' rows are internal
    warehouse transfers, not real supplier purchases, and must be excluded or
    a transfer's SupplierCode-shaped warehouse code can collide with a real
    supplier's code).

    See qty_check_rows for why backfill_is_offer runs first."""
    backfill_is_offer(store_name)
    codes = _supplier_codes(supplier_code)
    if not codes:
        return []
    if mode == "stock":
        sql = (
            "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.OrgOrderQty, om.TotalStock, "
            "om.SLSQty, om.UnitDescription, om.SaleUnit, om.MRP, om.WantedType, "
            "om.Remarks, om.PurchasePrice, om.SubLocation, om.ProductTypeName, "
            "om.MaxQty, om.Status, om.Qtycheck, "
            "SS.Stock AS S_Stock, SS.discound AS Discount, SS.MINQTY AS MinQty, "
            "SS.sch AS Sch, SS.free AS Free, SS.SupplierProductName, "
            "SS.SupplierProductCode, ISNULL(SS.Rack, '') AS Rack, om.IsOffer "
            "FROM OrderManagement om "
            + _supplier_stock_apply(codes, "CROSS APPLY", in_stock_only=True)
            + "WHERE om.storename = ? AND om.status = 0 AND om.orderqty > 0 "
            "ORDER BY om.ProductName"
        )
        params = (*codes, store_name)
    else:
        # EXISTS (not a JOIN) so a product with several historical purchase
        # lines from this supplier still shows exactly once. InvoiceSeries<>
        # 'TI' excludes internal warehouse transfers (see docstring).
        #
        # supplier_code is split in Python, NOT via dbo.SplitString(...) in
        # SQL: SplitString is a multi-statement table-valued function, which
        # SQL Server can't inline into the plan. Called from inside a
        # correlated EXISTS against PurchaseTrans (1M+ rows), that forces a
        # per-row procedural re-evaluation instead of a set-based semi-join.
        # A plain parametrized IN (?, ?, ...) list avoids that.
        #
        # pt.ProductCode is explicitly cast to om.ProductCode's side (not the
        # reverse) for the same reason as the product_mapping timeout fix
        # (see memory: non-sargable CASTs): OrderManagement.ProductCode is
        # FLOAT but PurchaseTrans.ProductCode is INT. `pt.ProductCode =
        # om.ProductCode` implicitly converts every pt.ProductCode to FLOAT
        # (float outranks int in SQL Server's type precedence), which makes
        # the predicate non-sargable and forces a full scan of PurchaseTrans
        # PER OrderManagement ROW instead of a seek on
        # IX_PurchaseTrans_Product_Store_Date -- this, not SplitString, was
        # the actual cause of the 45s timeout (confirmed: still slow after
        # removing SplitString alone, until this cast was added). Casting
        # om.ProductCode to INT instead keeps pt.ProductCode untouched and
        # seekable.
        placeholders = _in_list(codes)
        sql = (
            f"SELECT {_WORKSPACE_COLS}, om.IsOffer "
            "FROM OrderManagement om "
            "WHERE om.Status = 0 AND om.OrderQty > 0 "
            "AND om.ProductTypeName IN ('Pharma', 'Non Pharma') AND om.StoreName = ? "
            "AND EXISTS (SELECT 1 FROM PurchaseTrans pt WITH (NOLOCK) "
            "  WHERE pt.ProductCode = CAST(om.ProductCode AS INT) AND pt.StoreName = om.StoreName "
            "  AND pt.InvoiceSeries <> 'TI' "
            f"  AND pt.SupplierCode IN ({placeholders})) "
            "ORDER BY om.ProductTypeName, om.ProductName"
        )
        params = (store_name, *codes)

    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        result = [dict(zip(cols, row)) for row in cur.fetchall()]

    if mode == "stock":
        # Flag rows sourced from the NMW/Ho_code pseudo-supplier (see
        # sync_supplier_product_match_from_mapping) so the UI can highlight
        # "this is warehouse-backed stock, not a real supplier" distinctly.
        store = get_store(store_name)
        is_warehouse_stock = bool(store and store.get("ho_code") == supplier_code)
        for row in result:
            row["is_warehouse_stock"] = is_warehouse_stock
    return result


def all_open_orderables(store_name):
    """Every still-open, orderable product (status=0, orderqty>0, Pharma/Non
    Pharma) regardless of any supplier's purchase history or live stock.

    Backs the By Supplier grid's "Load all products" toggle: the per-supplier
    history/stock match has a known false-negative (picking the wrong one of
    several same-named OrderSuppliers entries shows 0 history for a product the
    supplier genuinely carries), so the operator needs a way to see the full
    open list and still assign a missed product to the picked supplier. Same
    PascalCase projection + offer flag as orders_by_supplier's history branch,
    so the grid renders it identically (minus the per-supplier stock columns,
    which don't exist for an unmatched product).

    See qty_check_rows for why backfill_is_offer runs first."""
    backfill_is_offer(store_name)
    sql = (
        f"SELECT {_WORKSPACE_COLS}, om.IsOffer "
        "FROM OrderManagement om "
        "WHERE om.Status = 0 AND om.OrderQty > 0 "
        "AND om.ProductTypeName IN ('Pharma', 'Non Pharma') AND om.StoreName = ? "
        "ORDER BY om.ProductTypeName, om.ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def orders_by_supplier_export_count(store_name, supplier_code):
    """Lightweight row count for the same stock-mode eligibility the Export
    button always acts on (see orders_by_supplier's mode='stock' branch and
    order_export.export_order) -- status=0, orderqty>0, live SupplierStock
    match with Stock>0. Exists so the UI can show/enable Export accurately
    without fetching the full stock grid just to count it, and independent of
    whichever History/Live Stock tab happens to be on screen."""
    codes = _supplier_codes(supplier_code)
    if not codes:
        return 0
    sql = (
        "SELECT COUNT(*) FROM OrderManagement om "
        + _supplier_stock_apply(codes, "CROSS APPLY", in_stock_only=True)
        + "WHERE om.storename = ? AND om.status = 0 AND om.orderqty > 0"
    )
    params = (*codes, store_name)
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0


def assigned_orders(store_name, supplier_code):
    """Port of Form1.FetchSupplierOrderDetails -- rows already assigned to this
    supplier (status=1). See qty_check_rows for why backfill_is_offer runs
    first."""
    backfill_is_offer(store_name)
    assigned = _assigned_code_values(supplier_code)
    sql = (
        "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.OrgOrderQty, om.SaleUnit, om.MRP, om.OrSupplier, "
        "om.Remarks, om.PurchasePrice, om.TotalStock, om.SLSQty, om.UnitDescription, om.WantedType, om.ProductTypeName, om.Status, om.IsOffer, om.Qtycheck "
        "FROM OrderManagement om "
        "WHERE om.status = 1 AND om.orderqty > 0 AND om.storename = ? "
        f"AND om.orsuppliercode IN ({_in_list(assigned)}) "
        "ORDER BY om.ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name, *assigned)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def all_assigned_orders(store_name):
    """Every assigned row (status=1, orderqty>0) for the store across ALL
    suppliers at once -- the "All Suppliers" view of Supplier Order Details,
    for reviewing the whole day's orders in one grid instead of switching
    supplier by supplier. Same shape as assigned_orders(), just without the
    supplier_code filter (OrSupplier is included so the grid can show which
    supplier each row went to, since that's no longer implied by a single
    picked supplier).

    See qty_check_rows for why backfill_is_offer runs first."""
    backfill_is_offer(store_name)
    sql = (
        "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.OrgOrderQty, om.SaleUnit, om.MRP, om.OrSupplier, "
        "om.Remarks, om.PurchasePrice, om.TotalStock, om.SLSQty, om.UnitDescription, om.WantedType, om.ProductTypeName, om.Status, om.IsOffer, om.Qtycheck "
        "FROM OrderManagement om "
        "WHERE om.status = 1 AND om.orderqty > 0 AND om.storename = ? "
        "ORDER BY om.OrSupplier, om.ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def assigned_orders_with_supplier_stock(store_name, supplier_code):
    """assigned_orders() plus the supplier's own live stock for each line
    (SupplierStock.Stock, via SupplierProductMatch -- same join
    orders_by_supplier's mode='stock' and orders_by_supplier_export_count
    already use). A LEFT JOIN, not INNER: a product with no
    SupplierProductMatch row at all is just as "not available from this
    supplier" as one matched with Stock=0, so both must come back (NULL
    supplier_stock), not be silently dropped."""
    codes = _supplier_codes(supplier_code) or [str(supplier_code or "")]
    assigned = _assigned_code_values(supplier_code)
    sql = (
        "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.SaleUnit, om.MRP, "
        "om.OrSupplier, om.Remarks, om.PurchasePrice, om.TotalStock, om.WantedType, "
        "om.ProductTypeName, om.Status, SS.Stock AS SupplierStock "
        "FROM OrderManagement om "
        + _supplier_stock_apply(codes, "OUTER APPLY", in_stock_only=False)
        + "WHERE om.status = 1 AND om.orderqty > 0 AND om.storename = ? "
        f"AND om.orsuppliercode IN ({_in_list(assigned)}) "
        "ORDER BY om.ProductName"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, *codes, store_name, *assigned)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def remove_unavailable_from_supplier(store_name, supplier_code, actor=None):
    """The operator exports an order to a supplier, then the supplier comes
    back saying some lines are out of stock. Rather than unassigning one
    product at a time, find every currently-assigned line for this supplier
    where the supplier's OWN live stock (SupplierStock.Stock) is <= 0 or
    unmatched, and drop them back to open (status=0, OrSupplier/
    OrSupplierCode=NULL) with qtycheck=1 so another supplier can pick them up
    without re-triggering the Qty Check review step. Returns the list of
    product codes actually removed."""
    rows = assigned_orders_with_supplier_stock(store_name, supplier_code)
    unavailable = [r for r in rows if not r.get("SupplierStock") or float(r["SupplierStock"]) <= 0]
    if not unavailable:
        return []
    product_codes = [r["ProductCode"] for r in unavailable]
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        placeholders = ",".join("?" for _ in product_codes)
        assigned = _assigned_code_values(supplier_code)
        order_ids = cur.execute(
            f"SELECT ProductCode, OrderId FROM ordermanagement "
            f"WHERE storename = ? AND productcode IN ({placeholders})",
            store_name, *product_codes,
        ).fetchall()
        order_id_by_code = {row.ProductCode: row.OrderId for row in order_ids}
        cur.execute(
            f"UPDATE ordermanagement SET orqty = NULL, orsupplier = NULL, "
            f"orsuppliercode = NULL, status = 0, qtycheck = 1 "
            f"WHERE storename = ? AND status = 1 AND orsuppliercode IN ({_in_list(assigned)}) "
            f"AND productcode IN ({placeholders})",
            store_name, *assigned, *product_codes,
        )
        for code in product_codes:
            order_id = order_id_by_code.get(code)
            if order_id is not None:
                _record_line_audit(
                    cur, store_name, int(order_id), code, "SUPPLIER_UNASSIGNED_STOCKOUT",
                    supplier_code, None, actor,
                )
        conn.commit()
    return product_codes


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


def bulk_assign_rows(store_name, supplier_code, supplier_name, product_codes, actor=None):
    """Set-based bulk version of assign_supplier's status 0->1 branch -- ports
    Form1.UpdateDatabase(), which looped every dgvMain row and ran the same
    per-row UPDATE (see Form1.vb ~line 4782). product_codes must already be
    resolved server-side (e.g. via orders_by_supplier) -- never trust a
    client-supplied list, since that would bypass the store/supplier/
    orderqty>0 scoping orders_by_supplier already enforces."""
    if not product_codes:
        return 0
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        placeholders = ",".join("?" for _ in product_codes)
        cur.execute(
            "UPDATE ordermanagement SET orqty = orderqty, orsupplier = ?, "
            "orsuppliercode = ?, status = 1 "
            "WHERE storename = ? AND status = 0 AND orderqty > 0 "
            f"AND productcode IN ({placeholders})",
            supplier_name, supplier_code, store_name, *product_codes,
        )
        assigned_count = cur.rowcount
        order_id = _latest_order_id(cur, store_name)
        if order_id is not None:
            for code in product_codes:
                _record_line_audit(
                    cur, store_name, order_id, code, "SUPPLIER_ASSIGNED_BULK",
                    None, supplier_code, actor,
                )
        conn.commit()
        return assigned_count


# ---- Bulk Assign · Best Margin (Order Workspace process after Qty Check) ----
# Owner rule (2026-10-25): every reviewed, still-unassigned line (the Pending
# Order set: qtycheck = 1, status = 0, orderqty > 0) goes to the supplier
# with the best margin over the product's last 5 supplies (real supplier
# invoices, series IV, GRN-level). Margin = (MRP - net cost) / MRP, with the
# net cost spread over received + free qty. A product with no usable supply
# (never received, or only from inactive suppliers) falls back to its most
# frequent supplier -- all-time purchase receipts first, then past order
# assignments in OrderManagementBackup. PurchaseTrans.Margin is NULL on every
# row, so the margin is computed here, never read from it.

AUTO_ASSIGN_LAST_SUPPLIES = 5

_AUTO_ASSIGN_PENDING_SQL = (
    "SELECT productcode, productname, orderqty FROM ordermanagement "
    "WHERE storename = ? AND qtycheck = 1 AND status = 0 AND orderqty > 0 "
    "AND producttypename IN ('Pharma', 'Non Pharma')"
)


def receipt_margin(mrp, item_cost, received, free):
    """Margin % of one supply: (MRP - net unit cost) / MRP, where the net
    cost is ItemCost spread over received + free qty. None when MRP or cost
    is missing."""
    mrp = float(mrp or 0)
    cost = float(item_cost or 0)
    received = float(received or 0)
    free = float(free or 0)
    if mrp <= 0 or cost <= 0 or received <= 0:
        return None
    net = cost * received / (received + max(free, 0))
    return (mrp - net) / mrp * 100


def pick_auto_assign_supplier(receipts, frequent, active):
    """receipts: the product's last supplies, newest first, as dicts with
    supplier_code / margin / grn_date. frequent: supplier codes, most
    frequent first (the fallback). active: {supplier_code: name} of this
    store's active OrderSuppliers. Returns (code, basis, margin, supplies):
    the best-margin supplier among the receipts, judged on each supplier's
    most recent supply (ties -> more of the 5 supplies, then most recent);
    else the first active frequent supplier; else (None, None, None, 0)."""
    per = {}
    for r in receipts:
        code = r["supplier_code"]
        if code not in active or r["margin"] is None:
            continue
        s = per.get(code)
        if s is None:
            per[code] = {"margin": r["margin"], "count": 1,
                         "latest": r["grn_date"] or datetime.date.min}
        else:
            s["count"] += 1
    if per:
        code = max(per, key=lambda c: (round(per[c]["margin"], 2), per[c]["count"], per[c]["latest"]))
        return code, "best_margin", per[code]["margin"], per[code]["count"]
    for code in frequent:
        if code in active:
            return code, "most_frequent", None, 0
    return None, None, None, 0


def auto_assign_proposals(store_name):
    """Proposed supplier for every Pending Order line (see the rule above).
    Read-only; auto_assign_apply recomputes it before writing."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        pending = cur.execute(_AUTO_ASSIGN_PENDING_SQL, store_name).fetchall()
        if not pending:
            return {"rows": [], "last_supplies": AUTO_ASSIGN_LAST_SUPPLIES}
        active = {
            str(r[0]).strip(): (r[1] or "").strip()
            for r in cur.execute(
                "SELECT suppliercode, Suppliername FROM OrderSuppliers WITH (NOLOCK) "
                "WHERE StoreName = ? AND ISNULL(IsActive, 1) = 1", store_name,
            ).fetchall()
            if r[0] is not None
        }
        receipts = {}
        for r in cur.execute(
            "WITH pend AS (" + _AUTO_ASSIGN_PENDING_SQL + "), "
            "grn AS ("
            "  SELECT pt.ProductCode, RTRIM(pt.SupplierCode) AS SupplierCode, pt.Grnnumber, "
            "  CAST(pt.GRNDate AS date) AS GRNDate, MAX(pt.MRP) AS MRP, "
            "  SUM(pt.ItemCost * pt.StockReceived) / NULLIF(SUM(pt.StockReceived), 0) AS ItemCost, "
            "  SUM(pt.StockReceived) AS Received, SUM(ISNULL(pt.FreeQty, 0)) AS Free "
            "  FROM PurchaseTrans pt WITH (NOLOCK) JOIN pend ON pend.productcode = pt.ProductCode "
            "  WHERE pt.StoreName = ? AND RTRIM(pt.InvoiceSeries) = 'IV' AND pt.StockReceived > 0 "
            "  GROUP BY pt.ProductCode, RTRIM(pt.SupplierCode), pt.Grnnumber, CAST(pt.GRNDate AS date)"
            "), ranked AS ("
            "  SELECT *, ROW_NUMBER() OVER (PARTITION BY ProductCode ORDER BY GRNDate DESC, Grnnumber DESC) AS rn "
            "  FROM grn"
            ") "
            "SELECT ProductCode, SupplierCode, GRNDate, MRP, ItemCost, Received, Free "
            "FROM ranked WHERE rn <= ? ORDER BY ProductCode, rn",
            store_name, store_name, AUTO_ASSIGN_LAST_SUPPLIES,
        ).fetchall():
            receipts.setdefault(int(r[0]), []).append({
                "supplier_code": str(r[1] or "").strip(),
                "grn_date": r[2],
                "margin": receipt_margin(r[3], r[4], r[5], r[6]),
            })
        frequent = {}
        for r in cur.execute(
            "WITH pend AS (" + _AUTO_ASSIGN_PENDING_SQL + ") "
            "SELECT pt.ProductCode, RTRIM(pt.SupplierCode), COUNT(DISTINCT pt.Grnnumber) AS n, MAX(pt.GRNDate) "
            "FROM PurchaseTrans pt WITH (NOLOCK) JOIN pend ON pend.productcode = pt.ProductCode "
            "WHERE pt.StoreName = ? AND RTRIM(pt.InvoiceSeries) = 'IV' AND pt.StockReceived > 0 "
            "GROUP BY pt.ProductCode, RTRIM(pt.SupplierCode) "
            "UNION ALL "
            "SELECT b.ProductCode, RTRIM(b.OrSupplierCode), -COUNT(*), MAX(b.OrderId) "
            "FROM OrderManagementBackup b WITH (NOLOCK) JOIN pend ON pend.productcode = b.ProductCode "
            "WHERE b.StoreName = ? AND b.OrSupplierCode IS NOT NULL "
            "GROUP BY b.ProductCode, RTRIM(b.OrSupplierCode)",
            store_name, store_name, store_name,
        ).fetchall():
            # Purchase counts are positive, assignment counts negative, so
            # sorting by (purchases first, count desc) is one key.
            frequent.setdefault(int(r[0]), []).append((r[2] > 0, abs(r[2]), str(r[1] or "").strip()))

    rows = []
    for p in pending:
        code = int(p[0])
        ranked = [c for _, _, c in sorted(frequent.get(code, []), key=lambda f: (f[0], f[1]), reverse=True)]
        supplier, basis, margin, supplies = pick_auto_assign_supplier(receipts.get(code, []), ranked, active)
        rows.append({
            "product_code": code,
            "product_name": p[1],
            "order_qty": p[2],
            "supplier_code": supplier,
            "supplier_name": active.get(supplier) if supplier else None,
            "basis": basis,
            "margin": None if margin is None else round(margin, 2),
            "supplies": supplies,
            "supplies_seen": len(receipts.get(code, [])),
        })
    rows.sort(key=lambda r: (r["supplier_name"] is None, r["supplier_name"] or "", r["product_name"] or ""))
    return {"rows": rows, "last_supplies": AUTO_ASSIGN_LAST_SUPPLIES}


def auto_assign_apply(store_name, product_codes=None, actor=None):
    """Assign the proposals from auto_assign_proposals -- recomputed here,
    never taken from the client. product_codes (optional) limits it to the
    lines the operator left ticked. Same status 0 -> 1 write as
    bulk_assign_rows, re-checking qtycheck = 1 / orderqty > 0 so a line
    changed since the preview is skipped."""
    wanted = None if product_codes is None else {int(c) for c in product_codes}
    groups = {}
    for p in auto_assign_proposals(store_name)["rows"]:
        if not p["supplier_code"] or (wanted is not None and p["product_code"] not in wanted):
            continue
        groups.setdefault((p["supplier_code"], p["supplier_name"]), []).append(p)
    if not groups:
        return {"assigned": 0, "suppliers": 0}
    assigned = 0
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        order_id = _latest_order_id(cur, store_name)
        for (supplier_code, supplier_name), items in groups.items():
            codes = [p["product_code"] for p in items]
            for i in range(0, len(codes), 500):
                chunk = codes[i:i + 500]
                placeholders = ",".join("?" for _ in chunk)
                cur.execute(
                    "UPDATE ordermanagement SET orqty = orderqty, orsupplier = ?, "
                    "orsuppliercode = ?, status = 1 "
                    "WHERE storename = ? AND status = 0 AND qtycheck = 1 AND orderqty > 0 "
                    f"AND productcode IN ({placeholders})",
                    supplier_name, supplier_code, store_name, *chunk,
                )
                assigned += cur.rowcount
            if order_id is not None:
                for p in items:
                    _record_line_audit(
                        cur, store_name, order_id, p["product_code"], "SUPPLIER_ASSIGNED_AUTO",
                        None, f"{supplier_code} ({p['basis']})", actor,
                    )
        conn.commit()
    return {"assigned": assigned, "suppliers": len(groups)}


def qty_check_rows(store_name):
    """Port of Form1.GetQtyCheckQuery('All', 'All') -- the Qty Check screen's
    main grid: only rows not yet reviewed (qtycheck = 0, status = 0) that
    actually order something -- owner ruling 2026-10-25: Or Qty 0 lines are
    not loaded for review (they are "no need" lines; _workflow_counts no
    longer counts them as pending, so they don't block Finalize).

    IsOffer is read directly off OrderManagement (set once per product at
    order-generation time -- see order_process.insert_data_into_destination /
    migration 0007) instead of recomputed here via a correlated EXISTS
    against PurchaseTrans. That subquery, run once per row on every grid
    load, measured at 77s for a store with 1385 open rows against a 278K-row
    PurchaseTrans table -- comfortably over the desktop client's 45s request
    timeout. LastOfferBaseQty/LastOfferFreeQty are left as a live OUTER APPLY
    for now (out of scope for this fix -- see repository.py history).

    backfill_is_offer(store_name) is called first (set-based UPDATE, ~1-2s
    even on NMW/NMA, 0.1s when nothing changed -- see timing note in that
    function's docstring) so a free-qty GRN posted after the order was last
    generated shows its 🎁 on this grid immediately, not just after the next
    order-generation run."""
    backfill_is_offer(store_name)
    sql = (
        "SELECT om.productcode, om.productname, om.orderqty, om.orgorderqty, om.totalstock, om.saleunit, om.unitdescription, "
        "om.slsqty, om.mrp, om.lastreceiveddate, om.lastsaledate, om.maxsaleqty, om.Transactiondate, om.wantedtype, "
        "om.producttypename, om.remarks, om.IsOffer, om.SkipReason, om.SkippedAt, "
        "lastoffer.LastOfferBaseQty, lastoffer.LastOfferFreeQty "
        "FROM ordermanagement om "
        f"{_LAST_OFFER_PATTERN_APPLY} "
        "WHERE om.qtycheck = 0 AND om.status = 0 AND om.orderqty > 0 AND om.storename = ? "
        "ORDER BY om.productname"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_skip_schema(cur)
        cur.execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def pending_order_rows(store_name):
    """Port of Form1.HandlePendingOrder -- the "Pending Order" screen's grid:
    every row already reviewed (qtycheck = 1) but not yet assigned to a
    supplier (status = 0) -- owner ruling (2026-10-13): no orderqty filter,
    a "no need" (orderqty = 0) line that's still open still belongs on this
    screen. Restricted to Pharma/Non Pharma like the VB combo's "All" option
    (the only two values that ever appear). Always includes producttypename
    so callers can apply the All/Pharma/Non Pharma filter client-side -- same
    pattern as qty_check_rows -- instead of a network round-trip per filter
    change. See qty_check_rows for why backfill_is_offer runs first."""
    backfill_is_offer(store_name)
    sql = (
        "SELECT om.productcode, om.productname, om.orderqty, om.orgorderqty, om.totalstock, om.slsqty, om.unitdescription, "
        "om.saleunit, om.mrp, om.lastreceiveddate, om.lastsaledate, om.maxsaleqty, om.Transactiondate, om.wantedtype, "
        "om.producttypename, om.remarks, om.IsOffer, om.SkipReason, om.SkippedAt, "
        "lastoffer.LastOfferBaseQty, lastoffer.LastOfferFreeQty "
        "FROM ordermanagement om "
        f"{_LAST_OFFER_PATTERN_APPLY} "
        "WHERE om.qtycheck = 1 AND om.status = 0 AND om.storename = ? "
        "AND om.producttypename IN ('Pharma', 'Non Pharma') ORDER BY om.productname"
    )
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_skip_schema(cur)
        cur.execute(sql, store_name)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def backfill_is_offer(store_name):
    """Per-store refresh for OrderManagement.IsOffer. Originally a one-time
    backfill (migration 0007 adds the column defaulted to 0; existing rows
    from before this change needed this run once), it is now ALSO called by
    every Order Workspace grid read (qty_check_rows, pending_order_rows,
    orders_by_supplier, all_open_orderables, assigned_orders,
    all_assigned_orders) so a free-qty GRN posted to PurchaseTrans after the
    order was last generated shows up immediately instead of waiting for the
    next order-generation run.

    This is a set-based UPDATE (not the per-row correlated EXISTS that
    measured 77s and was rejected -- see qty_check_rows), so it's cheap even
    on the live DB: measured ~2s for NMW/NMA (whole-store scan touching
    every still-open row) and ~0.1s when nothing needs updating (idempotent,
    re-run after the first catch-up each cycle is nearly free).

    Safe to re-run -- idempotent, only ever sets IsOffer=1 where the live
    PurchaseTrans history says so, never clears an existing 1."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE om SET om.IsOffer = 1 "
            "FROM OrderManagement om "
            "WHERE om.StoreName = ? AND om.IsOffer = 0 "
            "AND EXISTS (SELECT 1 FROM PurchaseTrans pt WITH (NOLOCK) "
            "  WHERE pt.ProductCode = CAST(om.ProductCode AS INT) "
            "  AND pt.StoreName = om.StoreName "
            "  AND pt.InvoiceSeries <> 'TI' AND pt.FreeQty > 0)",
            store_name,
        )
        updated = cur.rowcount
        conn.commit()
        return updated


def reset_pending_qty_check(store_name, actor=None):
    """Bulk "Reset Pending" action for the Qty Check screen's latest order:
    rows already assigned to a supplier (Status = 1) are stamped qtycheck = 1
    so they can never reappear as pending; every other row (Status = 0, not
    yet assigned) has OrderQty reset back to its original generated value
    (OrgOrderQty), undoing any unsaved manual edits so Qty Check starts clean
    from the order-generation baseline."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        order_id = _latest_order_id(cur, store_name)
        if order_id is None:
            return {"assigned_marked": 0, "remaining_reset": 0}
        assigned_marked = cur.execute(
            "UPDATE ordermanagement SET qtycheck = 1 "
            "WHERE storename = ? AND orderid = ? AND status = 1 AND qtycheck = 0",
            store_name, order_id,
        ).rowcount
        remaining_reset = cur.execute(
            "UPDATE ordermanagement SET orderqty = orgorderqty "
            "WHERE storename = ? AND orderid = ? AND status = 0",
            store_name, order_id,
        ).rowcount
        _record_line_audit(
            cur, store_name, order_id, None, "RESET_PENDING",
            None, f"assigned_marked={assigned_marked}, remaining_reset={remaining_reset}", actor,
        )
        conn.commit()
        return {"assigned_marked": assigned_marked, "remaining_reset": remaining_reset}


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
        # Ordering a skipped line again (qty > 0) ends its skip -- the line's
        # mode and the carried store+product skip both clear.
        if order_qty > 0:
            _ensure_skip_schema(cur)
            cur.execute(
                "UPDATE ordermanagement SET SkipReason = NULL, SkippedAt = NULL, SkippedBy = NULL "
                "WHERE productcode = ? AND storename = ? AND status = 0 AND SkipReason IS NOT NULL",
                product_code, store_name,
            )
            _clear_active_skip(cur, store_name, product_code, "manual", actor)
        _record_line_audit(
            cur, store_name, int(row.OrderId), product_code, "QTY_REVIEWED",
            old_qty, order_qty, actor,
        )
        conn.commit()
        return {"order_qty": order_qty, "remarks": remark}


# ---------------------------------------------------------------------------
# Skip rules -- the platform's three skip modes (skipModes.ts) on OrderNMC.
# Schema: sql/0010_order_skip_rules.sql (applied here at runtime, once).
# ---------------------------------------------------------------------------

SKIP_MODES = {
    "current_refresh": "Current Order",
    "until_next_sales": "Until Next Sales",
    "until_next_demand": "Until Next Demand",
}
# Carried into newly generated orders until a real sale after the skip --
# 'current_refresh' never is (same rule as order_items_repository.
# carry_forward_skips on the platform).
PERSISTENT_SKIP_MODES = ("until_next_sales", "until_next_demand")

_SKIP_SCHEMA_READY = False


def _ensure_skip_schema(cur=None):
    """Apply sql/0010 once per process on its OWN connection and commit it --
    never inside the caller's transaction (a read path would roll the DDL
    back; the order-generation transaction must not be committed early).
    `cur` is accepted for call-site symmetry and ignored."""
    global _SKIP_SCHEMA_READY
    if _SKIP_SCHEMA_READY:
        return
    path = os.path.join(os.path.dirname(__file__), "sql", "0010_order_skip_rules.sql")
    with open(path, encoding="utf-8") as fh:
        script = fh.read()
    with database.get_central_connection() as conn:
        ddl = conn.cursor()
        for batch in [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.MULTILINE) if b.strip()]:
            ddl.execute(batch)
        conn.commit()
    _SKIP_SCHEMA_READY = True


def _clear_active_skip(cur, store_name, product_code, reason, actor):
    cur.execute(
        "UPDATE dbo.OrderProductSkip SET ClearedAt = GETDATE(), ClearedBy = ?, ClearReason = ? "
        "WHERE StoreName = ? AND ProductCode = ? AND ClearedAt IS NULL",
        actor, reason, store_name, product_code,
    )


def skip_product(store_name, product_code, mode, actor=None):
    """Skip one open line with a platform skip mode: Or Qty 0, reviewed
    (it lands in Rejected), the mode recorded on the line, and -- for the
    two persistent modes -- an active store+product skip that the next
    generated orders re-apply until the product sells again. Re-skipping
    with another mode replaces the previous one."""
    if mode not in SKIP_MODES:
        raise ValueError(f"Skip mode must be one of {', '.join(SKIP_MODES)}.")
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        _ensure_skip_schema(cur)
        row = cur.execute(
            "SELECT orderqty, OrderId FROM ordermanagement "
            "WHERE productcode = ? AND storename = ? AND status = 0",
            product_code, store_name,
        ).fetchone()
        if not row:
            return None
        old_qty = int(row[0]) if row[0] is not None else 0
        remark = f"Skipped - {SKIP_MODES[mode]}"
        cur.execute(
            "UPDATE ordermanagement SET orderqty = 0, qtycheck = 1, remarks = ?, "
            "SkipReason = ?, SkippedAt = GETDATE(), SkippedBy = ? "
            "WHERE productcode = ? AND storename = ? AND status = 0",
            remark, mode, actor, product_code, store_name,
        )
        _clear_active_skip(cur, store_name, product_code, "replaced", actor)
        if mode in PERSISTENT_SKIP_MODES:
            cur.execute(
                "INSERT INTO dbo.OrderProductSkip (StoreName, ProductCode, SkipReason, OrderId, SkippedBy) "
                "VALUES (?, ?, ?, ?, ?)",
                store_name, product_code, mode, int(row.OrderId), actor,
            )
        _record_line_audit(
            cur, store_name, int(row.OrderId), product_code, "QTY_SKIPPED",
            old_qty, 0, actor,
        )
        conn.commit()
        return {"order_qty": 0, "remarks": remark, "skip_reason": mode}


def apply_carried_skips(cur, store_name):
    """Called by order_process inside the order-generation transaction,
    right after the new OrderManagement rows are inserted (both LEGACY and
    RULEBOOK engines go through it). First ends every active skip whose
    product has sold since it was skipped, then re-applies the rest to the
    new order (Or Qty 0, reviewed -> Rejected, with the mode on the line).
    Returns the number of new lines re-skipped."""
    _ensure_skip_schema(cur)
    cur.execute(
        "UPDATE s SET ClearedAt = GETDATE(), ClearReason = 'sale' "
        "FROM dbo.OrderProductSkip s "
        "WHERE s.StoreName = ? AND s.ClearedAt IS NULL "
        "AND EXISTS (SELECT 1 FROM ProductSaleInformation ps WITH (NOLOCK) "
        "  WHERE ps.StoreName = s.StoreName AND ps.ProductCode = s.ProductCode "
        "  AND ps.SeriesTransID = 1 AND ps.TransactionValidity = 0 AND ps.Quantity > 0 "
        "  AND ps.TransactionDate > s.SkippedAt)",
        store_name,
    )
    cur.execute(
        "UPDATE om SET om.OrderQty = 0, om.Qtycheck = 1, "
        "om.Remarks = 'Skipped - ' + CASE s.SkipReason WHEN 'until_next_sales' THEN 'Until Next Sales' "
        "  ELSE 'Until Next Demand' END, "
        "om.SkipReason = s.SkipReason, om.SkippedAt = s.SkippedAt, om.SkippedBy = s.SkippedBy "
        "FROM OrderManagement om "
        "JOIN dbo.OrderProductSkip s ON s.StoreName = om.StoreName AND s.ProductCode = om.ProductCode "
        "  AND s.ClearedAt IS NULL "
        "WHERE om.StoreName = ? AND om.Status = 0",
        store_name,
    )
    return cur.rowcount


def qty_check_purchase_details(store, product_code, mode):
    """Port of RetrieveDataForPurchaseDetailsAsync -- last 10 GRN/purchase
    lines for a product, from PurchaseTrans on either the central OrderNMC
    copy (mode='local') or the live branch DB (mode='remote')."""
    is_local = mode != "remote"
    supplier_table = "OrderSuppliers" if is_local else "Suppliers"
    supplier_store_filter = " AND sup.StoreName = ?" if is_local else ""
    store_filter = " AND pt.StoreName = ?" if is_local else ""
    # Extra fields for the Order Workspace's click-a-row purchase record card.
    # Central (local) PurchaseTrans only -- branch DBs have their own schema.
    detail_cols = (
        "pt.Grnnumber AS GRNNo, pt.InvoiceSeries, pt.SupplierCode, pt.BatchCode, pt.SaleUnit, "
        "pt.TaxAmount, pt.DiscountAmount, pt.Margin, " if is_local else ""
    )

    sql = (
        "SELECT TOP 10 pt.StockReceived AS RStock, pt.FreeQty, "
        "pt.ProductDiscPercent AS DIS, pt.ItemCost, pt.PurchasePrice AS PTR, "
        f"pt.MRP, pt.GRNDate, {detail_cols}"
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


def purchase_invoice_lines(store_name, grn_no, series, grn_date, supplier_code=None):
    """Every line of ONE purchase invoice / GRN (all its products), for the
    Order Workspace's click-a-purchase-row card. GRN numbers repeat across
    years (NMG GRN 4595 exists in 2024 and 2026), so the invoice is
    identified by store + GRN no + series + GRN date (+ supplier when known),
    never by the number alone. Product name / unit description / packing
    come from the store's Products master."""
    sql = (
        "SELECT pt.ProductCode, p.ProductName, p.UnitDescription, "
        "ISNULL(pt.SaleUnit, p.SaleUnit) AS SaleUnit, pt.StockReceived AS Qty, pt.FreeQty, "
        "pt.ProductDiscPercent AS DIS, pt.ItemCost, pt.PurchasePrice AS PTR, pt.MRP, pt.BatchCode "
        "FROM PurchaseTrans pt WITH (NOLOCK) "
        "LEFT JOIN Products p WITH (NOLOCK) ON p.StoreName = pt.StoreName AND p.ProductCode = pt.ProductCode "
        "WHERE pt.StoreName = ? AND pt.Grnnumber = ? AND RTRIM(pt.InvoiceSeries) = RTRIM(?) "
        "AND CAST(pt.GRNDate AS date) = CAST(? AS date)"
    )
    params = [store_name, grn_no, series or "", grn_date]
    if supplier_code:
        sql += " AND pt.SupplierCode = ?"
        params.append(str(supplier_code))
    sql += " ORDER BY p.ProductName"
    with database.get_central_connection() as conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def sale_bill_lines(store_name, bnumber, bill_date):
    """Every line of ONE sales bill (all its products) plus the bill header,
    for the Order Workspace's click-a-sales-row card. Bill numbers repeat
    too (NMG C01071089 exists in 2025 and 2026), so the bill date is part of
    the key."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        header = cur.execute(
            "SELECT TOP 1 s.BillNumber, s.BNumber, s.BillDate, s.Billtime, s.CustomerName, s.BillAmount, sr.Salesmanname "
            "FROM SaleInformation s WITH (NOLOCK) "
            "LEFT JOIN SalesRep sr WITH (NOLOCK) ON sr.Salesmancode = s.DeliverySalesRep AND sr.StoreName = s.StoreName "
            "WHERE s.StoreName = ? AND s.BNumber = ? AND CAST(s.BillDate AS date) = CAST(? AS date)",
            store_name, bnumber, bill_date,
        )
        hcols = [d[0] for d in header.description]
        hrow = header.fetchone()
        lines = cur.execute(
            "SELECT ps.ProductCode, p.ProductName, p.UnitDescription, p.SaleUnit, ps.Quantity AS Qty, "
            "ps.Freequantity AS FreeQty, ps.DiscountPercentage AS DIS, ps.Itemcost AS ItemCost, "
            "ps.PurchasePrice AS PTR, ps.MRP, ps.Rate, ps.Transactionamount AS Amount, "
            "ps.Batchdescription AS Batch, ps.Expirydate AS Expiry "
            "FROM ProductSaleInformation ps WITH (NOLOCK) "
            "LEFT JOIN Products p WITH (NOLOCK) ON p.StoreName = ps.StoreName AND p.ProductCode = ps.ProductCode "
            "WHERE ps.StoreName = ? AND ps.Bnumber = ? AND ps.TransactionValidity = 0 "
            "AND CAST(ps.TransactionDate AS date) = CAST(? AS date) "
            "ORDER BY p.ProductName",
            store_name, bnumber, bill_date,
        )
        lcols = [d[0] for d in lines.description]
        return {
            "header": dict(zip(hcols, hrow)) if hrow else None,
            "lines": [dict(zip(lcols, r)) for r in lines.fetchall()],
        }


def qty_check_sales_details(store, product_code, mode):
    """Port of RetrieveDataForSalesDetailsAsync -- last 10 sale lines for a
    product, from ProductSaleInformation/SaleInformation/SalesRep.

    Pre-limits ProductSaleInformation to its 40 most recent rows for this
    product (via IX_ProductSaleInformation_Main -- an index seek on
    ProductCode/TransactionValidity/StoreName with TransactionDate as the 4th
    key column, already ordered) BEFORE joining out to SaleInformation/
    SalesRep and sorting. The original query joined+grouped+sorted ALL of a
    product's historical sale lines (by s.BillTime, not covered by any index
    that also covers the WHERE filter) before applying TOP 10 -- fine for a
    slow mover, but a measured 1.9s for a genuine fast-mover (KIT KAT RS.10/-,
    3.3M total rows in the table) during a 2026-10-17 10-product timing check.
    40 (not 10) leaves slack for the GROUP BY to ever collapse multiple PS
    rows into fewer billed lines without starving the final TOP 10."""
    is_local = mode != "remote"
    store_filter = " AND {alias}.StoreName = ?"

    sql = (
        ";WITH recent AS (\n"
        "  SELECT TOP 40 PS.Bnumber, PS.BillNumber, PS.TransactionDate, PS.quantity, "
        "PS.DiscountPercentage, PS.Seriesname, PS.mrp, PS.purchaseprice, PS.Lastadjustmentdate\n"
        "  FROM ProductSaleInformation PS WITH (NOLOCK)\n"
        "  WHERE PS.ProductCode = ? AND PS.TransactionValidity = 0"
        + (store_filter.format(alias="PS") if is_local else "") + "\n"
        "  ORDER BY PS.TransactionDate DESC\n"
        ")\n"
        "SELECT TOP 10 SUM(r.quantity) AS TotalQuantity, s.Billtime AS Bill_Time, "
        "sr.Salesmanname, s.CUSTOMERNAME, r.DiscountPercentage AS dis, "
        "r.Seriesname AS type, r.mrp, r.purchaseprice AS ptr, r.Bnumber "
        "FROM recent r "
        "INNER JOIN saleinformation s ON r.BillNumber = s.BillNumber AND r.TransactionDate = s.BillDate"
        + (store_filter.format(alias="s") if is_local else "") + " "
        "INNER JOIN SalesRep sr ON s.DeliverySalesRep = sr.Salesmancode"
        + (store_filter.format(alias="sr") if is_local else "") + " "
        "GROUP BY r.Bnumber, s.BillTime, s.CUSTOMERNAME, r.Seriesname, r.mrp, "
        "r.purchaseprice, r.Lastadjustmentdate, r.DiscountPercentage, sr.Salesmanname "
        "ORDER BY s.BillTime DESC"
    )
    params = [product_code]
    if is_local:
        params.append(store["store_name"])
    if is_local:
        params.append(store["store_name"])
    if is_local:
        params.append(store["store_name"])

    conn = database.get_central_connection() if is_local else database.get_branch_connection(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    with conn:
        cur = conn.cursor().execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _clean_qty(value):
    """Exact integers stay ints; fractional (AllowFractions products) keep 3 dp.
    Never abbreviate -- the chart shows the real quantity, 1300 not 1.3K."""
    if value is None:
        return 0
    f = float(value)
    return int(f) if f == int(f) else round(f, 3)


def qty_check_monthly_stats(store, product_code, mode):
    """Port of RetrieveDataForChartAsync -- the "Monthly Statistics" chart source,
    enriched with the return breakdown the legacy WinForms chart never surfaced.

    ProductTrans is the POS's OWN pre-aggregated monthly rollup. Verified against
    371k consecutive month-pairs from the live copy, the closing-stock identity

        opening + PurchaseQuantity + TransferInQuantity
                - SaleQuantity - TransferOutQuantity + AdjustmentQuantity  ==  StockInHand

    reconciles at 99.7% (residual is the rare tid-17 'N' series + a few data
    anomalies -- NOT returns). That proves returns are ALREADY absorbed:

        * SaleQuantity      is NET of sales returns  (the 'R' / tid-2 series)
        * AdjustmentQuantity folds expiry returns    (the 'ER' / tid-16 series),
          and is SIGNED (negative adjustments are preserved, never abs()'d)
        * PurchaseQuantity  is already net of purchase returns

    So the movement model the chart draws is:

        IN         = purchase + transfer_in
        OUT        = sales (net) + transfer_out
        ADJUSTMENT = adjustment (signed)
        STOCK      = stock (closing StockInHand)

    We DO NOT re-add returns to those totals -- that would double count. We only
    expose them for the tooltip so it can explain how a net figure was reached.
    sales_return/expiry_return are read straight from the raw
    ProductSaleInformation series (already synced centrally, no schema change
    needed). purchase_return reads ProductTrans.PurchaseReturnQuantity directly
    (added by sql/0004_producttrans_return_columns.sql + the matching
    sync_engine.py projection change -- same row as PurchaseQuantity, so no
    purchase/pack-unit conversion is involved, unlike PurchaseTrans's own
    'PR' series which is stored in purchase units and would need a per-product
    conversion factor to line up). Until that migration has been applied AND
    a sync cycle has repopulated the month, the column reads NULL and this
    coerces to 0 -- indistinguishable from a genuine zero-return month for
    that transitional window."""
    is_local = mode != "remote"
    pt_store = " AND pt.StoreName = ?" if is_local else ""
    ps_store = " AND ps.StoreName = ?" if is_local else ""
    # Same window + ascending ordering as the legacy query: last ~3 month starts.
    boundary = "DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 3, 0)"

    stats_sql = (
        "SELECT CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120) AS ym, "
        "ISNULL(pt.PurchaseQuantity, 0) AS purchase, "
        "ISNULL(pt.TransferInQuantity, 0) AS transfer_in, "
        "ISNULL(pt.SaleQuantity, 0) AS sales, "
        "ISNULL(pt.TransferOutQuantity, 0) AS transfer_out, "
        "ISNULL(pt.AdjustmentQuantity, 0) AS adjustment, "
        "ISNULL(pt.StockInHand, 0) AS stock, "
        "ISNULL(pt.PurchaseReturnQuantity, 0) AS purchase_return_signed "
        "FROM ProductTrans pt WITH (NOLOCK) "
        "WHERE pt.ProductCode = ? "
        f"AND pt.MonthOfStatistics >= {boundary}{pt_store} "
        "ORDER BY pt.MonthOfStatistics ASC"
    )
    # Sales returns ('R') and expiry returns ('ER') per month, signed as stored
    # (both come through negative). These are the ONLY return figures that
    # reconcile in base units; everything else is read from ProductTrans above.
    returns_sql = (
        "SELECT CONVERT(VARCHAR(7), ps.TransactionDate, 120) AS ym, "
        "SUM(CASE WHEN ps.SeriesName = 'R'  THEN ps.Quantity ELSE 0 END) AS r_signed, "
        "SUM(CASE WHEN ps.SeriesName = 'ER' THEN ps.Quantity ELSE 0 END) AS er_signed "
        "FROM ProductSaleInformation ps WITH (NOLOCK) "
        "WHERE ps.ProductCode = ? AND ps.TransactionValidity = 0 "
        "AND ps.SeriesName IN ('R', 'ER') "
        f"AND ps.TransactionDate >= {boundary}{ps_store} "
        "GROUP BY CONVERT(VARCHAR(7), ps.TransactionDate, 120)"
    )
    stats_params = [product_code] + ([store["store_name"]] if is_local else [])
    returns_params = [product_code] + ([store["store_name"]] if is_local else [])

    conn = database.get_central_connection() if is_local else database.get_branch_connection(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    with conn:
        cur = conn.cursor()
        cur.execute(stats_sql, stats_params)
        stat_rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
        cur.execute(returns_sql, returns_params)
        returns = {r[0]: (r[1] or 0.0, r[2] or 0.0) for r in cur.fetchall()}

    rows = []
    for s in stat_rows:
        ym = s["ym"]
        r_signed, er_signed = returns.get(ym, (0.0, 0.0))
        sales_return = _clean_qty(-float(r_signed))    # >= 0; stock came IN, already netted out of `sales`
        expiry_return = _clean_qty(-float(er_signed))  # >= 0; stock went OUT, already inside `adjustment`
        purchase = _clean_qty(s["purchase"])            # NET of purchase returns
        transfer_in = _clean_qty(s["transfer_in"])
        sales = _clean_qty(s["sales"])                 # NET of sales returns
        transfer_out = _clean_qty(s["transfer_out"])
        adjustment = _clean_qty(s["adjustment"])       # SIGNED, includes expiry returns
        stock = _clean_qty(s["stock"])
        # PurchaseReturnQuantity is stored <= 0 on the same ProductTrans row as
        # PurchaseQuantity (added by sql/0004_producttrans_return_columns.sql),
        # so this needs no unit conversion, unlike PurchaseTrans's own 'PR'
        # series (purchase/pack units). Reads 0 pre-migration/pre-resync -- see
        # the function docstring.
        purchase_return = _clean_qty(-float(s["purchase_return_signed"]))
        gross_purchase = _clean_qty(purchase + purchase_return)  # purchase before the return
        gross_sales = _clean_qty(sales + sales_return)            # sales before the return
        # total_in/total_out are built from the GROSS figures, not the net
        # `purchase`/`sales` fields -- a month can carry a return with no
        # offsetting purchase of its own (the original purchase landed in an
        # earlier month), which drives net `purchase` negative and would make
        # "stock coming in" a negative bar. Using gross figures keeps both
        # bars >= 0 while still reconciling exactly: the purchase_return and
        # sales_return terms cancel in (total_in - total_out), so
        # prevStock + total_in - total_out + adjustment == stock holds
        # identically either way (verified against live data both ways).
        rows.append({
            "month": ym,
            # --- the four series the chart draws ---
            "purchase": purchase,
            "transfer_in": transfer_in,
            "sales": sales,
            "transfer_out": transfer_out,
            "adjustment": adjustment,
            "stock": stock,
            "total_in": _clean_qty(gross_purchase + transfer_in + sales_return),
            "total_out": _clean_qty(gross_sales + transfer_out + purchase_return),
            # --- breakdown for the tooltip (already included above, shown for transparency) ---
            "gross_purchase": gross_purchase,
            "purchase_return": purchase_return,                       # inside `purchase` (net) already
            "gross_sales": gross_sales,
            "sales_return": sales_return,                             # inside `sales` (net) already
            "expiry_return": expiry_return,                           # inside `adjustment` already
            "stock_adjustment": _clean_qty(adjustment - float(er_signed)),  # adjustment excl. expiry
        })
    return rows


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


# --------------------------------------------------------------------------
# Restore by OrderId -- an explicit, admin-initiated recovery workflow, new
# in this module (the existing compare_previous_order* functions apply the
# VB.NET comparison HEURISTICS on top of a backup; this is an unconditional
# restore of a specific, operator-selected backup order back onto the
# matching current rows). See restore_backup_order below for the full
# safety contract.
# --------------------------------------------------------------------------

class RestoreValidationError(ValueError):
    """The selected backup cannot be safely restored as requested -- missing
    rows, wrong store, or some other precondition failed. Carries a plain
    message; never partially restores."""


def restorable_order_preview(store_name, order_id):
    """Everything restore_backup_order's confirmation screen needs to show
    before an operator commits: backup timestamp, product count, and the
    suppliers represented, scoped to (store_name, order_id) in
    OrderManagementBackup. Returns None if that (store, order) combination
    has no backup rows at all (nothing to restore)."""
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        header = cur.execute(
            "SELECT COUNT(*) AS ProductCount, MAX(WantedDate) AS BackedUpAt "
            "FROM OrderManagementBackup WHERE StoreName = ? AND OrderId = ?",
            store_name, order_id,
        ).fetchone()
        if not header or not header.ProductCount:
            return None
        suppliers = previous_order_suppliers(store_name, order_id)
        return {
            "store_name": store_name,
            "order_id": order_id,
            "product_count": int(header.ProductCount),
            "backed_up_at": header.BackedUpAt,
            "suppliers": suppliers,
        }


def restore_backup_order(store_name, order_id, actor):
    """Restore a specific, operator-selected backup order's rows back onto
    the current OrderManagement rows for the same products, for this store.

    This is unconditional (unlike compare_previous_order's VB heuristics):
    every matching product's OrQty/OrderQty/OrgOrderQty/OrSupplier/
    OrSupplierCode/Status/QtyCheck/Remarks/WantedType is overwritten from the
    backup row -- "restore" means restore, not re-apply a comparison rule.

    Never infers the source snapshot from MAX(OrderId); order_id is always
    the caller's explicit selection (see schemas.RestoreBackupOrderRequest /
    router.restore_backup_order), matching the requirement that a restore
    must never silently pick "the latest" on the caller's behalf.

    Safety sequence, all inside one transaction:
      1. Takes the SAME per-store applock as the processing lock / unlock /
         destructive write (_with_store_applock) -- a concurrent Order
         Process run or unlock for this store blocks until this restore's
         transaction ends, and vice versa; they can never interleave.
      2. Re-validates the backup exists for this exact (StoreName, OrderId)
         -- never trusts a preview the caller may have fetched a while ago.
      3. Requires every backup row to have a matching current OrderManagement
         row by ProductCode (same store) -- if the backup contains ANY
         product with no corresponding live row, this is reported as
         insufficient information and the whole restore is refused (no
         partial writes), per "If existing backup rows do not contain
         sufficient information for accurate restoration, block the
         operation."
      4. Applies the restore as one set-based UPDATE...FROM...JOIN (so the
         whole operation is atomic -- not a product-by-product loop that
         could partially apply).
      5. Writes one audit row per restored product (old Status/OrQty ->
         new) plus one summary row, and commits.
      6. Returns the restored row count, verified against the SAME COUNT
         the UPDATE's own rowcount reported.

    Raises RestoreValidationError (never partially restores) if the backup
    is missing, empty, or any product in it has no corresponding live row.
    Raises PendingExportBlocked if the CURRENT order has any Status = 0
    lines -- restoring backup data onto those rows (by ProductCode match)
    could silently discard an in-progress qty-check edit. This is a hard,
    non-overridable block specific to restore (see PendingExportBlocked's
    docstring for why it is NOT the same warn+admin-override gate Order
    Process uses) -- the caller simply retries once those lines are
    resolved; there is no separate "unlock" action.
    """
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _ensure_workflow_schema(cur)
        try:
            # require_no_pending_export_on_connection takes the same
            # per-store applock as Order Process's short-lived concurrency
            # guard (@LockOwner = 'Transaction', so it also serializes this
            # restore against a concurrent Process run for this store), AND
            # refuses to proceed if the current order has pending Status = 0
            # lines -- restoring over them could silently discard in-
            # progress review.
            require_no_pending_export_on_connection(cur, store_name)

            backup_rows = cur.execute(
                "SELECT ProductCode, ProductName, OrQty, OrderQty, OrgOrderQty, "
                "OrSupplier, OrSupplierCode, Status, QtyCheck, Remarks, WantedType "
                "FROM OrderManagementBackup WHERE StoreName = ? AND OrderId = ?",
                store_name, order_id,
            ).fetchall()
            if not backup_rows:
                raise RestoreValidationError(
                    f"No backup exists for '{store_name}' order #{order_id}."
                )

            backup_codes = [r.ProductCode for r in backup_rows]
            placeholders = ", ".join("?" for _ in backup_codes)
            live_codes = {
                r[0] for r in cur.execute(
                    f"SELECT ProductCode FROM OrderManagement "
                    f"WHERE StoreName = ? AND ProductCode IN ({placeholders})",
                    store_name, *backup_codes,
                ).fetchall()
            }
            missing = [code for code in backup_codes if code not in live_codes]
            if missing:
                sample = ", ".join(str(c) for c in missing[:10])
                raise RestoreValidationError(
                    f"{len(missing)} product(s) in backup order #{order_id} have no "
                    f"matching current order row for '{store_name}' (e.g. {sample}) -- "
                    "cannot restore without overwriting an unrelated/nonexistent row. "
                    "Refusing to partially restore."
                )

            # Snapshot old values for the per-row audit trail before they're
            # overwritten -- read as part of this same transaction so it
            # reflects exactly the rows about to change, not a stale read.
            current_order_id_row = cur.execute(
                "SELECT DISTINCT OrderId FROM OrderManagement "
                f"WHERE StoreName = ? AND ProductCode IN ({placeholders})",
                store_name, *backup_codes,
            ).fetchall()
            current_order_ids = {int(r.OrderId) for r in current_order_id_row if r.OrderId is not None}

            old_values = {
                r.ProductCode: {"Status": r.Status, "OrQty": r.OrQty}
                for r in cur.execute(
                    f"SELECT ProductCode, Status, OrQty FROM OrderManagement "
                    f"WHERE StoreName = ? AND ProductCode IN ({placeholders})",
                    store_name, *backup_codes,
                ).fetchall()
            }

            cur.execute(
                """
                UPDATE om SET
                    om.OrQty = omb.OrQty,
                    om.OrderQty = omb.OrderQty,
                    om.OrgOrderQty = omb.OrgOrderQty,
                    om.OrSupplier = omb.OrSupplier,
                    om.OrSupplierCode = omb.OrSupplierCode,
                    om.Status = omb.Status,
                    om.QtyCheck = omb.QtyCheck,
                    om.Remarks = omb.Remarks,
                    om.WantedType = omb.WantedType
                FROM OrderManagement om
                INNER JOIN OrderManagementBackup omb
                    ON om.ProductCode = omb.ProductCode AND om.StoreName = omb.StoreName
                WHERE omb.StoreName = ? AND omb.OrderId = ?
                """,
                store_name, order_id,
            )
            restored_count = cur.rowcount

            for current_order_id in current_order_ids:
                _record_line_audit(
                    cur, store_name, current_order_id, None, "ORDER_RESTORED",
                    f"source_order_id={order_id}",
                    f"restored_products={restored_count}", actor,
                )
            for row in backup_rows:
                old = old_values.get(row.ProductCode, {})
                target_order_id = next(iter(current_order_ids), order_id)
                _record_line_audit(
                    cur, store_name, target_order_id, row.ProductCode, "ORDER_LINE_RESTORED",
                    f"status={old.get('Status')},orqty={old.get('OrQty')}",
                    f"status={row.Status},orqty={row.OrQty}", actor,
                )

            conn.commit()
            return {
                "store_name": store_name,
                "source_order_id": order_id,
                "restored_count": restored_count,
                "actor": actor,
            }
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
