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
import os
import re
import threading
import time

import pyodbc

from modules.legacy_order import database

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")

_DEADLOCK_SQLSTATE = "40001"
_DEADLOCK_RETRIES = 3
_DEADLOCK_BACKOFF_SECONDS = 2

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


def fetch_source_data(conn_str, odata, store_name, store_code, min_days, max_days, mode):
    """Port of FetchSourceData. Returns (columns, rows)."""
    sql = _load_sql("order_remote" if mode == "remote" else "order_local")
    sql, values = _bind(sql, {
        "minday": min_days,
        "maxday": max_days,
        "storename": store_name,
        "storecode": store_code,
        "ODATA": odata,
        "status": 0,
    })

    with pyodbc.connect(conn_str, timeout=30) as conn:
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

    # Multiple stores' one-click runs can land in this transaction at the same
    # time; all writes are scoped to StoreName so a deadlocked attempt is safe
    # to redo from scratch rather than needing the whole job to fail. The
    # in-process lock below removes the concurrent-writer race for this app;
    # the retry loop stays as a safety net for anything still writing to
    # OrderManagement outside this process (e.g. the legacy desktop app).
    with _write_lock:
        for attempt in range(1, _DEADLOCK_RETRIES + 1):
            with pyodbc.connect(database.central_connection_string(), timeout=30) as conn:
                conn.timeout = 0
                cur = conn.cursor()
                try:
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
                    conn.commit()
                    return len(payload)
                except pyodbc.Error as exc:
                    conn.rollback()
                    sqlstate = exc.args[0] if exc.args else None
                    if sqlstate == _DEADLOCK_SQLSTATE and attempt < _DEADLOCK_RETRIES:
                        time.sleep(_DEADLOCK_BACKOFF_SECONDS * attempt)
                        continue
                    raise


def update_order_header_details(source_cs, store_name, min_days, max_days):
    """Port of UpdateOrderHeaderDetails.

    Last sale bill and last GRN always come from the BRANCH database, even when
    the order query itself ran in local mode -- they are the watermarks that
    later tell the GRN reconciliation where this order stopped.
    """
    last_sale_bill_no = ""
    last_bill_datetime = None
    last_grn = ""

    with pyodbc.connect(source_cs, timeout=30) as src:
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

    with pyodbc.connect(database.central_connection_string(), timeout=30) as conn:
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


def run_order_process(store, min_days, max_days, mode, on_progress=None):
    """Port of ProcessOrder + the FetchOrderData worker branch."""
    def report(msg):
        if on_progress:
            on_progress(msg)

    odata = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    source_cs = database.branch_connection_string(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    query_cs = source_cs if mode == "remote" else database.central_connection_string()

    report(f"Fetching order data ({mode} mode, since {odata})...")
    columns, rows = fetch_source_data(
        query_cs, odata, store["store_name"], store["store_code"],
        min_days, max_days, mode,
    )
    report(f"Order query returned {len(rows)} rows.")

    report("Backing up and rewriting OrderManagement...")
    inserted = insert_data_into_destination(columns, rows, store["store_name"])

    report("Stamping OrderHeaderDetails...")
    header = update_order_header_details(
        source_cs, store["store_name"], min_days, max_days
    )

    report(f"Order processing completed ({inserted} rows).")
    return {"rows": inserted, "odata": odata, "header": header}
