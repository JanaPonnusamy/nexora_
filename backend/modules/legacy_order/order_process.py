"""Python port of the legacy Order Process (Form1.ProcessOrder).

Flow, unchanged from VB:

    1. FetchSourceData        -- run the 90-day min/max order query
    2. InsertDataIntoDestination
         a. copy the store's current OrderManagement rows to OrderManagementBackup
         b. delete the store's OrderManagement rows
         c. bulk-insert the freshly computed rows
         d. neutralise the 'Additional Row' entries (qty 0, Status 2)
    3. UpdateOrderHeaderDetails -- stamp an OrderHeaderDetails audit row

The order query itself lives in sql/order_local.sql and sql/order_remote.sql,
lifted verbatim from Form1.vb. Two modes, matching the VB radio buttons:

    local  -- run against OrderNMC's own synced copy, filtered by @storename
    remote -- run straight against the branch DB (no StoreName column there)

Note the legacy app does NOT use sp_GenerateBranchOrder; that SP is a simpler,
stale variant. The inline query is the real rule engine and is the one ported.
"""
import datetime
import logging
import os
import re
import threading
import time

import pyodbc

from modules.legacy_order import database
from modules.legacy_order import repository

logger = logging.getLogger(__name__)

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")

# NMW is the only source legacy_order refreshes warehouse-stock from today
# (see repository.replace_supplier_stock / sync_supplier_product_match_from_mapping).
# Env-overridable to match service.WAREHOUSE_STORES if that set ever grows.
_WAREHOUSE_STOCK_SOURCE = os.getenv("LEGACY_WAREHOUSE_STOCK_SOURCE", "NMW")

_DEADLOCK_SQLSTATE = "40001"
_DEADLOCK_RETRIES = 3
_DEADLOCK_BACKOFF_SECONDS = 2

# A momentary WAN/VPN blip to a remote branch SQL Server surfaces while pyodbc
# is still *opening* the connection: an 08S01 communication link failure or an
# HYT00/HYT01 connect timeout (classically "TCP Provider ... (10060)" raised on
# SQLSetConnectAttr(SQL_ATTR_AUTOCOMMIT)). update_order_header_details always
# reaches back out to the branch after the long sync, so a single dropped packet
# there used to hard-fail the whole one-click run even though the OrderManagement
# rewrite had already committed. Retry the connect itself a few times with
# backoff before giving up.
_TRANSIENT_CONN_SQLSTATES = {"08S01", "08001", "08003", "HYT00", "HYT01"}
_CONNECT_RETRIES = 3
_CONNECT_BACKOFF_SECONDS = 2


def _connect(conn_str, timeout=30):
    """pyodbc.connect with retry on transient connection failures."""
    for attempt in range(1, _CONNECT_RETRIES + 1):
        try:
            return pyodbc.connect(conn_str, timeout=timeout)
        except pyodbc.Error as exc:
            sqlstate = exc.args[0] if exc.args else None
            if sqlstate in _TRANSIENT_CONN_SQLSTATES and attempt < _CONNECT_RETRIES:
                time.sleep(_CONNECT_BACKOFF_SECONDS * attempt)
                continue
            raise

# start_order_process (service.py) fires one thread per store, and every
# store's InsertDataIntoDestination hits the SAME shared OrderManagement
# table. Without an index, the backup INSERT...SELECT and the DELETE below
# scan the whole table (not just this store's rows), so two stores' scans
# overlap and SQL Server picks one as a deadlock victim (1205). Indexing
# StoreName narrows the scans to seeks, but serializing this block in-process
# removes the race entirely rather than just shrinking it.
_write_lock = threading.Lock()

# OrderManagement column mappings from InsertDataIntoDestination's SqlBulkCopy.
# (source column in the query result -> OrderManagement column). OrderQty is
# deliberately mapped twice: OrgOrderQty preserves the computed quantity so a
# later manual edit to OrderQty can still be compared against the original.
COLUMN_MAP = [
    ("productcode", "ProductCode"),
    ("productname", "ProductName"),
    ("TotalStock", "TotalStock"),
    ("SaleUnit", "SaleUnit"),
    ("slsqty", "SLSQty"),
    ("PurchasePrice", "PurchasePrice"),
    ("MRP", "MRP"),
    ("UnitDescription", "UnitDescription"),
    ("SubLocation", "SubLocation"),
    ("producttype", "ProductType"),
    ("LastReceivedDate", "LastReceivedDate"),
    ("LastSaleDate", "LastSaleDate"),
    ("MaxSaleQty", "MaxSaleQty"),
    ("Transactiondate", "Transactiondate"),
    ("WantedDate", "WantedDate"),
    ("storename", "StoreName"),
    ("StoreCode", "StoreCode"),
    ("OrderId", "OrderId"),
    ("MinQty", "MinQty"),
    ("MaxQty", "MaxQty"),
    ("WantedType", "WantedType"),
    ("OrderQty", "OrderQty"),
    ("OrderQty", "OrgOrderQty"),
    ("productTypeName", "ProductTypeName"),
    ("Frequence", "Frequence"),
    ("Status", "Status"),
]

_PARAM_RE = re.compile(r"@(\w+)")


def _bind(sql, params):
    """Rewrite @named params to pyodbc's positional ? and order the values.

    Lets the ported SQL stay byte-for-byte identical to the VB literal.
    """
    values = []

    def sub(match):
        name = match.group(1)
        key = next((k for k in params if k.lower() == name.lower()), None)
        if key is None:
            raise KeyError(f"Unbound parameter @{name}")
        values.append(params[key])
        return "?"

    return _PARAM_RE.sub(sub, sql), values


def _load_sql(name):
    with open(os.path.join(_SQL_DIR, f"{name}.sql"), encoding="utf-8") as fh:
        return fh.read()


def fetch_source_data(conn_str, odata, store_name, store_code, min_days, max_days,
                      mode, recency_days=10, sql_name=None):
    """Port of FetchSourceData. Returns (columns, rows).

    ``sql_name`` overrides the file (used for ``order_warehouse`` -- see
    run_order_process); otherwise it's the retail local/remote query, unchanged.
    ``recencydays`` is only referenced by order_warehouse.sql; binding it for the
    retail queries is harmless because _bind only substitutes params that appear
    in the SQL text.
    """
    if sql_name is None:
        sql_name = "order_remote" if mode == "remote" else "order_local"
    sql = _load_sql(sql_name)
    sql, values = _bind(sql, {
        "minday": min_days,
        "maxday": max_days,
        "storename": store_name,
        "storecode": store_code,
        "ODATA": odata,
        "status": 0,
        "recencydays": recency_days,
    })

    with _connect(conn_str, timeout=30) as conn:
        conn.timeout = 0
        cur = conn.cursor()
        cur.execute(sql, values)
        columns = [d[0] for d in cur.description]
        return columns, cur.fetchall()


def insert_data_into_destination(columns, rows, store_name):
    """Port of InsertDataIntoDestination: backup -> delete -> insert -> flag."""
    index = {c.lower(): i for i, c in enumerate(columns)}
    missing = [src for src, _ in COLUMN_MAP if src.lower() not in index]
    if missing:
        raise ValueError(f"Order query result is missing columns: {missing}")

    dest_cols = [dest for _, dest in COLUMN_MAP]
    picks = [index[src.lower()] for src, _ in COLUMN_MAP]
    payload = [tuple(r[i] for i in picks) for r in rows]
    order_id_pos = dest_cols.index("OrderId")
    new_order_ids = {row[order_id_pos] for row in payload}

    # Multiple stores' one-click runs can land in this transaction at the same
    # time; all writes are scoped to StoreName so a deadlocked attempt is safe
    # to redo from scratch rather than needing the whole job to fail. The
    # in-process lock below removes the concurrent-writer race for this app;
    # the retry loop stays as a safety net for anything still writing to
    # OrderManagement outside this process (e.g. the legacy desktop app).
    with _write_lock:
        for attempt in range(1, _DEADLOCK_RETRIES + 1):
            with _connect(database.central_connection_string(), timeout=30) as conn:
                conn.timeout = 0
                cur = conn.cursor()
                try:
                    # Short-lived concurrency guard, INSIDE this same
                    # transaction, immediately before the destructive writes
                    # below: takes the per-store sp_getapplock (@LockOwner =
                    # 'Transaction') so a second, concurrent Process run (or
                    # a concurrent restore_backup_order call) for this exact
                    # store blocks until this transaction commits or rolls
                    # back. This is ONLY the requirement-9 concurrency lock
                    # that prevents two simultaneous processing runs -- there
                    # is no durable "pending-export business lock" anymore
                    # (that table/unlock-admin-action mechanism was removed;
                    # pending Status = 0 lines are now a request-time WARNING
                    # the caller already confirmed past in service.
                    # start_order_process, not something re-checked again
                    # here at write time).
                    repository._with_store_applock(cur, store_name)

                    # Audit signal (not a separate backup mechanism -- the
                    # unconditional INSERT INTO OrderManagementBackup below
                    # already covers every row/status unconditionally): if
                    # more than one row on the order about to be overwritten
                    # is both reviewed and already assigned to a supplier,
                    # record that explicitly before it's gone.
                    repository.record_protected_backup_snapshot(
                        cur, store_name, repository._latest_order_id(cur, store_name),
                    )

                    # A re-run that lands on the same per-second OrderID as a
                    # run that already completed (retry after a client-side
                    # timeout, a double-submitted job, ...) would otherwise
                    # violate PK_OrderManagementBackup here: the prior run's
                    # backup copy for that (StoreName, OrderId) is already
                    # committed. It is a byte-for-byte duplicate of what we are
                    # about to insert, so clearing it first makes the backup
                    # step idempotent instead of aborting the whole order run.
                    #
                    # Two separate collisions are possible, so both are
                    # cleared: (1) the backup slot for OrderManagement's
                    # *current* OrderId (a prior run that got this far before),
                    # and (2) the backup slot for the *new* OrderId this run is
                    # about to produce (a prior attempt whose backup insert
                    # committed but then died before clearing OrderManagement,
                    # leaving a stale row under the id we're about to reuse).
                    cur.execute(
                        "DELETE b FROM OrderManagementBackup b "
                        "INNER JOIN OrderManagement om "
                        "ON om.StoreName = b.StoreName AND om.OrderId = b.OrderId "
                        "AND om.ProductCode = b.ProductCode "
                        "WHERE om.StoreName = ?",
                        store_name,
                    )
                    for new_order_id in new_order_ids:
                        cur.execute(
                            "DELETE FROM OrderManagementBackup "
                            "WHERE StoreName = ? AND OrderId = ?",
                            store_name,
                            new_order_id,
                        )
                    cur.execute(
                        "INSERT INTO OrderManagementBackup "
                        "SELECT * FROM OrderManagement WHERE StoreName = ?",
                        store_name,
                    )
                    cur.execute("DELETE FROM OrderManagement WHERE StoreName = ?", store_name)

                    if payload:
                        col_list = ", ".join(f"[{c}]" for c in dest_cols)
                        placeholders = ", ".join("?" for _ in dest_cols)
                        cur.fast_executemany = True
                        cur.executemany(
                            f"INSERT INTO OrderManagement ({col_list}) VALUES ({placeholders})",
                            payload,
                        )
                        cur.fast_executemany = False

                    cur.execute(
                        "UPDATE OrderManagement SET OrderQty = 0, OrgOrderQty = 0, Status = 2, "
                        "Remarks = 'Additional' "
                        "WHERE StoreName = ? AND WantedType = 'Additional Row'",
                        store_name,
                    )

                    # IsOffer: set once per product here, in a single
                    # set-based UPDATE, instead of recomputed live per grid
                    # row on every screen load (see migration 0007 for the
                    # full story -- that per-row EXISTS against PurchaseTrans
                    # measured at 77s for a 1385-row/278K-PurchaseTrans-row
                    # store, well over the desktop client's 45s timeout).
                    # This UPDATE still scans PurchaseTrans, but once per
                    # order-generation run for the store, not once per grid
                    # load -- the cost moves from "every time someone opens
                    # the screen" to "once when the order is generated".
                    if payload:
                        cur.execute(
                            "UPDATE om SET om.IsOffer = 1 "
                            "FROM OrderManagement om "
                            "WHERE om.StoreName = ? "
                            "AND EXISTS (SELECT 1 FROM PurchaseTrans pt WITH (NOLOCK) "
                            "  WHERE pt.ProductCode = CAST(om.ProductCode AS INT) "
                            "  AND pt.StoreName = om.StoreName "
                            "  AND pt.InvoiceSeries <> 'TI' AND pt.FreeQty > 0)",
                            store_name,
                        )
                    conn.commit()
                    return len(payload)
                except pyodbc.Error as exc:
                    conn.rollback()
                    sqlstate = exc.args[0] if exc.args else None
                    if sqlstate == _DEADLOCK_SQLSTATE and attempt < _DEADLOCK_RETRIES:
                        time.sleep(_DEADLOCK_BACKOFF_SECONDS * attempt)
                        continue
                    raise


def update_order_header_details(source_cs, store_name, min_days, max_days,
                                from_central=False):
    """Port of UpdateOrderHeaderDetails.

    Last sale bill and last GRN are the watermarks that later tell the GRN
    reconciliation where this order stopped.

    For LAN stores they come from the BRANCH database (``from_central`` False),
    even when the order query itself ran in local mode -- unchanged behaviour.

    For an agent-synced store (e.g. NMV, ``from_central`` True) HO has no direct
    branch SQL connection: the store's ProductSaleInformation / PurchaseTrans
    rows are already in the central OrderNMC copy, stamped with StoreName by the
    NMV Integration uplink. The two watermark reads therefore run against that
    central copy instead, scoped by ``StoreName`` so no other store's rows can
    leak in. The selected columns, ``'C%'`` / ``'IV'`` filters and ordering are
    otherwise identical to the branch reads.
    """
    last_sale_bill_no = ""
    last_bill_datetime = None
    last_grn = ""

    if from_central:
        # Already-synced NMV copy -- same columns/filters, StoreName-scoped.
        with _connect(database.central_connection_string(), timeout=30) as src:
            cur = src.cursor()
            row = cur.execute(
                "SELECT TOP 1 Transactiondate, BNumber FROM ProductSaleInformation "
                "WHERE StoreName = ? AND BNumber LIKE 'C%' "
                "ORDER BY Transactiondate DESC, BNumber DESC",
                store_name,
            ).fetchone()
            if row:
                last_sale_bill_no = str(row.BNumber or "")
                last_bill_datetime = row.Transactiondate

            row = cur.execute(
                "SELECT TOP 1 Grnnumber FROM Purchasetrans "
                "WHERE StoreName = ? AND InvoiceSeries = 'IV' ORDER BY Grndate DESC",
                store_name,
            ).fetchone()
            if row:
                last_grn = str(row.Grnnumber or "")
    else:
        with _connect(source_cs, timeout=30) as src:
            cur = src.cursor()
            row = cur.execute(
                "SELECT TOP 1 Transactiondate, BNumber FROM ProductSaleInformation "
                "WHERE BNumber LIKE 'C%' ORDER BY Transactiondate DESC, BNumber DESC"
            ).fetchone()
            if row:
                last_sale_bill_no = str(row.BNumber or "")
                last_bill_datetime = row.Transactiondate

            row = cur.execute(
                "SELECT TOP 1 Grnnumber FROM Purchasetrans WHERE InvoiceSeries = 'IV' "
                "ORDER BY Grndate DESC"
            ).fetchone()
            if row:
                last_grn = str(row.Grnnumber or "")

    with _connect(database.central_connection_string(), timeout=30) as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT TOP 1 WantedDate, OrderId, StoreName FROM OrderManagement "
            "WHERE StoreName = ? ORDER BY OrderId DESC",
            store_name,
        ).fetchone()
        # No rows, or a null WantedDate, means there is nothing to stamp: the VB
        # returned silently here rather than writing a header.
        if not row or row.WantedDate is None:
            return None

        wanted_date = row.WantedDate
        if not (datetime.datetime(1753, 1, 1) <= wanted_date <= datetime.datetime(9999, 12, 31)):
            return None

        or_store_name = row.StoreName
        order_id = int(row.OrderId)

        count = cur.execute(
            "SELECT COUNT(*) FROM OrderHeaderDetails "
            "WHERE StoreName = ? AND CONVERT(date, OrderDateTime) = ?",
            or_store_name,
            datetime.date.today(),
        ).fetchone()[0]
        order_no = count + 1 if count > 0 else 1

        cur.execute(
            "INSERT INTO OrderHeaderDetails (StoreName, OrderId, OrderNo, OrderDateTime, "
            "LastSaleBillNo, LastBillDateTime, LastGRN, MinDays, MaxDays) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            or_store_name, order_id, order_no, wanted_date,
            last_sale_bill_no, last_bill_datetime, last_grn, min_days, max_days,
        )
        conn.commit()

    return {"order_id": order_id, "order_no": order_no, "last_grn": last_grn,
            "last_sale_bill_no": last_sale_bill_no}


def refresh_warehouse_stock(store, source_store_name, on_progress=None):
    """Pull ``source_store_name``'s (e.g. NMW) live branch stock into this
    store's SupplierStock rows (central OrderNMC.SupplierStock, filed under
    this store's own Ho_code), then bridge SupplierProductMatch via
    dbo.product_mapping so the existing "Order Based Supplier Stock" join
    (repository.orders_by_supplier mode='stock') can actually surface it.

    Shared by service._run_stock_update's background job and by
    run_order_process, which calls this automatically before every retail
    order generation so NMW's stock is never stale by the time a store's
    supplier-stock screen is checked.

    Returns (inserted, matched) row counts. Raises on failure -- the caller
    (run_order_process) wraps this in its own try/except so a stale/
    unreachable warehouse never blocks normal order generation; service's
    standalone stock-update job surfaces the raised error to its own job
    status instead.
    """
    def report(msg):
        if on_progress:
            on_progress(msg)

    source_store = repository.get_store(source_store_name)
    if not source_store:
        report(f"{source_store_name} is not configured in OrderNMC.Stores; skipping stock refresh.")
        return 0, 0
    report(f"Reading stock from {source_store_name}...")
    rows = repository.branch_stock(source_store)
    report(f"Read {len(rows)} products. Updating {store['store_name']}'s supplier stock...")
    # suppliercode is THIS store's own code for the source ("HO") supplier
    # (dbo.Stores.Ho_code), not the source store's name -- NMS/NMA file it
    # under '94', NMC under 'ST_2', NMG under '99', etc.
    inserted = repository.replace_supplier_stock(store["store_name"], store["ho_code"], rows)
    # Bridge SupplierProductMatch via product_mapping too -- without this,
    # the SupplierStock rows just inserted are unreachable from
    # orders_by_supplier(mode='stock') because that join requires a matching
    # SupplierProductMatch row, and NMW never gets one from the manual
    # Supplier Excel Mapping flow real suppliers use.
    matched = repository.sync_supplier_product_match_from_mapping(
        store["store_name"], store["ho_code"], source_store_name, rows,
    )
    report(f"{source_store_name} stock refreshed ({inserted} rows, {matched} product_mapping matches).")
    return inserted, matched


def run_order_process(store, min_days, max_days, mode, on_progress=None,
                      is_warehouse=False, recency_days=10, is_agent_synced=False):
    """Port of ProcessOrder + the FetchOrderData worker branch.

    A warehouse store (``is_warehouse``) runs the order_warehouse.sql query
    against the central OrderNMC copy. That query is StoreName-scoped (like
    order_local), counts Transfer-Out demand, and takes a configurable recency
    window -- see sql/order_warehouse.sql. Retail stores are untouched.

    An agent-synced store (``is_agent_synced``, e.g. NMV) has no direct branch
    SQL connection from HO -- its data arrives via the NMV Integration agent and
    is already in the central OrderNMC copy. The order query is therefore forced
    to local mode (reads the central copy, StoreName-scoped exactly like every
    other local run) and the header watermark reads come from central too
    (``from_central``). The 90-day CTE, min/max, quantity and status logic are
    byte-for-byte the same as every other local run -- only the data *source*
    differs. LAN stores are unaffected.
    """
    def report(msg):
        if on_progress:
            on_progress(msg)

    odata = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    source_cs = database.branch_connection_string(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    if is_warehouse:
        sql_name = "order_warehouse"
        # order_warehouse.sql filters by StoreName, which only the central copy
        # has -- the branch DB has no StoreName column.
        query_cs = database.central_connection_string()
        mode_label = "warehouse"
    elif is_agent_synced:
        # No branch to query -- the retail order query runs against the central
        # copy the NMV Integration agent already populated. Forced local;
        # source_cs is built but never used (update_order_header_details reads
        # central instead).
        sql_name = None
        mode = "local"
        query_cs = database.central_connection_string()
        mode_label = "agent-synced"
    else:
        sql_name = None
        query_cs = source_cs if mode == "remote" else database.central_connection_string()
        mode_label = mode

    if not is_warehouse and store["store_name"] != _WAREHOUSE_STOCK_SOURCE and store["ho_code"]:
        try:
            refresh_warehouse_stock(store, _WAREHOUSE_STOCK_SOURCE, report)
        except Exception as exc:
            logger.exception("warehouse stock refresh failed for %s", store["store_name"])
            report(f"{_WAREHOUSE_STOCK_SOURCE} stock refresh failed (continuing order generation): {exc}")

    report(f"Fetching order data ({mode_label} mode, since {odata})...")
    columns, rows = fetch_source_data(
        query_cs, odata, store["store_name"], store["store_code"],
        min_days, max_days, mode, recency_days=recency_days, sql_name=sql_name,
    )
    report(f"Order query returned {len(rows)} rows.")

    # The pending-supplier-assignment warning was already confirmed (or
    # admin-overridden) at request time in service.start_order_process --
    # there is nothing left to re-check here. insert_data_into_destination
    # still takes the short-lived per-store applock inside its own
    # transaction purely to prevent a second concurrent Process run (or a
    # concurrent restore) for this store, not to re-validate any business
    # rule.
    report("Backing up and rewriting OrderManagement...")
    inserted = insert_data_into_destination(columns, rows, store["store_name"])

    report("Stamping OrderHeaderDetails...")
    header = update_order_header_details(
        source_cs, store["store_name"], min_days, max_days,
        from_central=is_agent_synced,
    )

    report(f"Order processing completed ({inserted} rows).")
    return {"rows": inserted, "odata": odata, "header": header}
