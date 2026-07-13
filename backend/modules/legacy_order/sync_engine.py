"""Python port of the legacy ``CentralSyncHelper.vb``.

Pulls rows from a branch SQL Server into the central OrderNMC database,
stamping each row with StoreName/Sync/SyncDateTime, via a per-batch staging
table + MERGE. The SELECT statements, the incremental max-ID watermarks and
the MERGE key sets are reproduced verbatim from the VB implementation --
changing any of them changes what the Order Process later reads.

VB -> Python notes:
  * SqlBulkCopy has no pyodbc equivalent; ``executemany`` with
    ``fast_executemany`` is used to load the staging table instead.
  * Like VB, a failed batch MERGE does not abort the table -- the remaining
    batches still run. Unlike VB, the failure is returned to the caller instead
    of only being written to the console, so a partially merged table cannot
    quietly report success.
"""
import datetime
import decimal
import uuid

import pyodbc

BATCH_SIZE = 10000

# Source table -> destination table in OrderNMC, copied exactly from Form1's
# `tablesToSync`. Two things here are load-bearing and must not be "tidied":
#
#   * Suppliers lands in OrderSuppliers, NOT Suppliers.
#   * SaleInformation runs BEFORE ProductSaleInformation. Its watermark is
#     PSI's max ID minus 1000, so it deliberately reads the PREVIOUS run's PSI
#     high-water mark. Sync PSI first and bill headers get skipped.
#
# TAX is absent for the same reason it was in VB: it has no ProductCode, so the
# merge's fallback key set never matched and the merge threw -- an exception the
# VB outer try/catch swallowed. TAX has therefore never actually synced.
TABLE_PLAN = [
    ("Products", "Products"),
    ("SaleInformation", "SaleInformation"),
    ("ProductTrans", "ProductTrans"),
    ("PurchaseTrans", "PurchaseTrans"),
    ("ProductSaleInformation", "ProductSaleInformation"),
    ("SalesRep", "SalesRep"),
    ("Suppliers", "OrderSuppliers"),
    ("Batches", "Batches"),
    ("SupplierProductMatch", "SupplierProductMatch"),
]

SYNCABLE_TABLES = [src for src, _ in TABLE_PLAN]


def get_query_for_table(table_name):
    """Verbatim port of CentralSyncHelper.GetQueryForTable."""
    if table_name == "Products":
        return (
            "SELECT ProductCode, ProductName, DivisionCode, ManufacturerCode, SupplierCode, "
            "UnitDescription, AllowFractions, MinimumStockLevel, MaximumStockLevel, ScheduleCode, "
            "MRP, PurchasePrice, PurchaseUnit, PurchaseTaxCode, SalePrice, SaleUnit, SalesTaxCode, "
            "TotalStock, Remarks, ProductType, TaxId, ItemCost, SubLocation, CreationDate, "
            "ModifiedDate, isActive, OrderDate, OrderTime, FreeQuantity "
            "FROM Products WHERE isActive = 1"
        )
    if table_name == "ProductSaleInformation":
        return (
            "SELECT PS.ProductCode, PS.Quantity, PS.ID, PS.TransactionDate, PS.SeriesTransID, "
            "PS.TransactionValidity, PS.DontConsiderInOrder, PS.Bnumber, PS.SeriesName, PS.MRP, "
            "PS.PurchasePrice, PS.DiscountPercentage, PS.LastAdjustmentDate, PS.BillNumber, "
            "ps.Batchdescription, PS.ExpiryDate, ps.rate1 "
            "FROM ProductSaleInformation PS "
            "WHERE PS.ID > ? AND PS.TransactionValidity = 0"
        )
    if table_name == "Suppliers":
        return (
            "SELECT DISTINCT suppliercode, suppliername, mobilenumber, email "
            "FROM Suppliers WHERE IsActive = 1"
        )
    if table_name == "Batches":
        return (
            "SELECT ProductCode, Stock, MRP, ExpiryDate, ItemCost, PurchasePrice, SaleUnit, "
            "GrnDate, LastReceivedDate, LastSaleDate, BatchCode, SalesTaxCode, SupplierCode, Rate1 "
            "FROM Batches WHERE Stock > 0"
        )
    if table_name == "ProductTrans":
        return (
            "WITH LastThreeMonths AS ("
            "  SELECT * FROM ProductTrans "
            "  WHERE MonthOfStatistics >= DATEADD(MONTH, -4, GETDATE())"
            ") "
            "SELECT MonthOfStatistics, SaleQuantity, StockInHand, PurchaseQuantity, "
            "AdjustmentQuantity, LastBillDate, LastGrnDate, ProductCode, TransferInQuantity, "
            "TransferOutQuantity FROM LastThreeMonths "
            "WHERE StockInHand IS NOT NULL AND PurchaseQuantity IS NOT NULL "
            "AND SaleQuantity IS NOT NULL AND AdjustmentQuantity IS NOT NULL "
            "ORDER BY ProductCode, MonthOfStatistics"
        )
    if table_name == "PurchaseTrans":
        return (
            "SELECT PT.ID, p.productcode, P.ProductType, pt.stockreceived, pt.FreeQty, "
            "ProductDiscPercent, pt.itemcost, pt.purchaseprice, pt.mrp, pt.grndate, "
            "pt.InvoiceSeries, pt.Grnnumber, s.suppliername, pt.suppliercode "
            "FROM PurchaseTrans pt "
            "INNER JOIN suppliers s ON pt.suppliercode = s.suppliercode "
            "INNER JOIN products p ON p.productcode = pt.productcode "
            "WHERE pt.id > ? ORDER BY pt.id DESC"
        )
    if table_name == "SaleInformation":
        return (
            "SELECT SI.BillDate, SI.BillNumber, SI.BNumber, SI.BillAmount, SI.CustomerName, "
            "SI.DeliverySalesRep, SI.Billtime, SI.CustomerCode "
            "FROM SaleInformation SI "
            "WHERE EXISTS ("
            "    SELECT 1 FROM ProductSaleInformation PS "
            "    WHERE PS.ID > ? "
            "      AND PS.TransactionValidity = 0 "
            "      AND PS.BNumber = SI.BNumber "
            "      AND PS.TransactionDate = SI.BillDate"
            ") "
            "ORDER BY SI.BillDate, SI.BillNumber"
        )
    if table_name == "SalesRep":
        return (
            "SELECT DISTINCT Salesmancode, Salesmanname, CreationDate, ModifiedDate "
            "FROM SalesRep WHERE isactive = 1"
        )
    if table_name == "TAX":
        return "SELECT taxcode, description FROM TAX"
    if table_name == "SupplierProductMatch":
        return (
            "SELECT suppliercode, supplierproductcode, supplierproductname, productcode, "
            "username, lastmodifieddate, isactive FROM SupplierProductMatch"
        )
    raise ValueError(f"Unknown table: {table_name}")


def merge_keys(dest_table, columns):
    """Verbatim port of the Select Case in CentralSyncHelper.GetMergeQuery."""
    have = {c.lower() for c in columns}

    def has(*names):
        return all(n.lower() in have for n in names)

    dest = dest_table.lower()
    if dest in ("productsaleinformation", "purchasetrans"):
        if has("ID", "StoreName"):
            return ["ID", "StoreName"]
    elif dest == "saleinformation":
        if has("BillNumber", "BillDate", "StoreName"):
            keys = ["BillNumber", "BillDate", "StoreName"]
            if has("CustomerCode"):
                keys.append("CustomerCode")
            return keys
    elif dest == "producttrans":
        if has("ProductCode", "MonthOfStatistics", "StoreName"):
            return ["ProductCode", "MonthOfStatistics", "StoreName"]
    elif dest in ("suppliers", "ordersuppliers"):
        if has("suppliercode", "StoreName"):
            return ["suppliercode", "StoreName"]
    elif dest == "salesrep":
        if has("Salesmancode", "StoreName"):
            return ["Salesmancode", "StoreName"]
    elif dest == "batches":
        if has("ProductCode", "BatchCode", "StoreName"):
            return ["ProductCode", "BatchCode", "StoreName"]
    elif dest == "supplierproductmatch":
        if has("suppliercode", "supplierproductcode", "StoreName"):
            return ["suppliercode", "supplierproductcode", "StoreName"]
    else:
        if has("ProductCode", "StoreName"):
            return ["ProductCode", "StoreName"]

    raise ValueError(f"No valid primary key columns found for merge into {dest_table}.")


def _sql_type(py_type):
    """Port of GetCreateTableQuery's DataColumn -> SQL type mapping."""
    if py_type is bool:
        return "BIT"
    if py_type is int:
        return "BIGINT"
    if py_type in (float, decimal.Decimal):
        return "FLOAT"
    if py_type is datetime.datetime:
        return "DATETIME"
    if py_type is datetime.date:
        return "DATE"
    return "NVARCHAR(MAX)"


def _is_string_type(py_type):
    return py_type not in (
        bool, int, float, decimal.Decimal, datetime.datetime, datetime.date,
    )


def _watermark(dest_cur, table_name, dest_table, store_name):
    """Port of STEP 1 -- the incremental max-ID watermark.

    SaleInformation keys off ProductSaleInformation's max ID minus a 1000-row
    safety margin (bills whose lines arrived in an earlier batch would
    otherwise never get their header row).
    """
    if table_name == "SaleInformation":
        row = dest_cur.execute(
            "SELECT ISNULL(MAX(ID), 0) FROM ProductSaleInformation WHERE StoreName = ?",
            store_name,
        ).fetchone()
        return max(0, int(row[0] or 0) - 1000)

    if table_name in ("ProductSaleInformation", "PurchaseTrans"):
        row = dest_cur.execute(
            f"SELECT ISNULL(MAX(ID), 0) FROM [{dest_table}] WHERE StoreName = ?",
            store_name,
        ).fetchone()
        return int(row[0] or 0)

    return None


def sync_table(source_cs, dest_cs, table_name, dest_table, store_name, on_progress=None):
    """Port of CentralSyncHelper.SyncTable.

    Returns (rows_fetched, batch_errors). batch_errors is empty on a clean run.
    """
    with pyodbc.connect(dest_cs, timeout=30) as dest_conn:
        dest_conn.timeout = 0
        dest_cur = dest_conn.cursor()

        # STEP 1 -- watermark
        param = _watermark(dest_cur, table_name, dest_table, store_name)

        # STEP 2 -- fetch new records from the branch
        select_sql = get_query_for_table(table_name)
        with pyodbc.connect(source_cs, timeout=30) as src_conn:
            src_conn.timeout = 0
            src_cur = src_conn.cursor()
            if param is None:
                src_cur.execute(select_sql)
            else:
                src_cur.execute(select_sql, param)

            src_columns = [d[0] for d in src_cur.description]
            src_types = [d[1] for d in src_cur.description]
            rows = src_cur.fetchall()

        total_rows = len(rows)
        if total_rows == 0:
            return 0, []

        # STEP 3 -- append the sync stamp columns
        columns = list(src_columns) + ["StoreName", "Sync", "SyncDateTime"]
        types = list(src_types) + [str, int, datetime.datetime]
        now = datetime.datetime.now()
        stamped = [tuple(r) + (store_name, 0, now) for r in rows]

        col_defs = ", ".join(f"[{c}] {_sql_type(t)}" for c, t in zip(columns, types))
        string_cols = {c for c, t in zip(columns, types) if _is_string_type(t)}

        # Batches is a full-replace snapshot: the branch only sends rows with
        # Stock > 0, so anything the MERGE does not touch must first be zeroed
        # or sold-out batches would keep their last-known stock forever.
        if dest_table.lower() == "batches":
            dest_cur.execute(
                "UPDATE Batches SET Stock = 0 WHERE StoreName = ?", store_name
            )
            dest_conn.commit()

        # STEP 4 -- stage + MERGE, one batch at a time
        errors = []
        for start in range(0, total_rows, BATCH_SIZE):
            batch = stamped[start:start + BATCH_SIZE]
            stage = f"{dest_table}_Stage_{uuid.uuid4().hex[:8]}"

            try:
                dest_cur.execute(
                    f"IF OBJECT_ID('{stage}', 'U') IS NOT NULL DROP TABLE [{stage}];"
                )
                dest_cur.execute(f"CREATE TABLE [{stage}] ({col_defs})")
                dest_conn.commit()

                placeholders = ", ".join("?" for _ in columns)
                insert_cols = ", ".join(f"[{c}]" for c in columns)
                dest_cur.fast_executemany = True
                dest_cur.executemany(
                    f"INSERT INTO [{stage}] ({insert_cols}) VALUES ({placeholders})",
                    batch,
                )
                dest_cur.fast_executemany = False

                # VB's "skip merge if the stage is empty" guard.
                staged = dest_cur.execute(
                    f"SELECT COUNT(1) FROM [{stage}]"
                ).fetchone()[0]
                if staged:
                    dest_cur.execute(
                        build_merge_sql(dest_table, stage, columns, string_cols)
                    )
                dest_conn.commit()
            except Exception as exc:
                # VB logged the failure and moved to the next batch. Preserve that,
                # but hand the error back so the job can report it.
                dest_conn.rollback()
                errors.append(f"batch at row {start}: {exc}")
            finally:
                dest_cur.fast_executemany = False
                try:
                    dest_cur.execute(
                        f"IF OBJECT_ID('{stage}', 'U') IS NOT NULL DROP TABLE [{stage}];"
                    )
                    dest_conn.commit()
                except Exception:
                    pass  # a leaked stage table must not mask the real error

            if on_progress:
                on_progress(min(start + BATCH_SIZE, total_rows), total_rows)

        return total_rows, errors


def build_merge_sql(dest_table, stage_table, columns, string_cols):
    """Port of CentralSyncHelper.GetMergeQuery's SQL assembly."""
    keys = merge_keys(dest_table, columns)

    on_parts = []
    for k in keys:
        if k in string_cols:
            on_parts.append(
                f"T.[{k}] COLLATE SQL_Latin1_General_CP1_CI_AS = "
                f"S.[{k}] COLLATE SQL_Latin1_General_CP1_CI_AS"
            )
        else:
            on_parts.append(f"T.[{k}] = S.[{k}]")

    update_set = ", ".join(f"T.[{c}] = S.[{c}]" for c in columns if c not in keys)
    insert_cols = ", ".join(f"[{c}]" for c in columns)
    insert_vals = ", ".join(f"S.[{c}]" for c in columns)

    return (
        f"MERGE [{dest_table}] AS T USING [{stage_table}] AS S "
        f"ON {' AND '.join(on_parts)} "
        f"WHEN MATCHED THEN UPDATE SET {update_set} "
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals});"
    )
