"""Builds and replaces the per-store SQLite order cache after Order Process.

Design doc: docs/order-sync-redesign/Order_Sync_Redesign_Plan.md section 3.3.
Standalone -- reads central OrderNMC/OrderSMS/OrderSuccess via the SAME
database.get_central_connection() already used elsewhere in legacy_order
(not re-imported logic from any other module), but the SQL here is
self-contained, not called out to repository.py, so this cache module has
no runtime dependency on repository.py's own evolution.

Lifecycle (plan doc 3.3):
  1. Order Process finishes for a store.
  2. build_cache_for_store() reads that order's lines + per-product history
     + export state from central, writes them into a NEW sqlite file at a
     temp path.
  3. Before swapping the temp file into the real path, drain_writeback()
     is called on the OLD file (if any) to push any pending local edits to
     central first -- replace never silently drops an edit in flight.
  4. Only then is the old file deleted and the new one moved into place.
"""
import datetime
import decimal
import json
import logging
import os
import sqlite3
import tempfile
import threading

from .. import database
from . import schema, writeback

logger = logging.getLogger(__name__)

CACHE_DIR_ENV = "NEXORA_ORDER_CACHE_DIR"

# One lock per store: a supplier-stock refresh (view endpoint) must not write
# into a file the Order Process build is swapping out at the same moment.
_STORE_LOCKS = {}
_STORE_LOCKS_GUARD = threading.Lock()


def store_lock(store_name):
    with _STORE_LOCKS_GUARD:
        return _STORE_LOCKS.setdefault(str(store_name).upper(), threading.Lock())


def cache_path(store_name):
    base = os.environ.get(CACHE_DIR_ENV) or os.path.join(
        os.environ.get("NEXORA_INSTALL_PATH", "."), "order_cache"
    )
    # Multi-tenant HO (.32: Success + SMS both have an SMA): a tenant on its
    # own legacy database keeps its caches in a sub-folder named after it, so
    # one tenant's store can never overwrite another's. The default database
    # (single-tenant HOs) keeps the flat layout.
    db = database.active_database_name()
    if db and db.upper() != os.getenv("LEGACY_DB_DATABASE", "OrderNMC").upper():
        base = os.path.join(base, "".join(c if c.isalnum() else "_" for c in db))
    os.makedirs(base, exist_ok=True)
    safe_store = "".join(c if c.isalnum() else "_" for c in str(store_name))
    return os.path.join(base, f"order_cache_{safe_store}.sqlite")


def _fetch_current_order(central_cur, store_name):
    """Current (latest, un-superseded) order's lines for this store. Column
    set matches repository.assigned_orders's verified real usage (OrderQty,
    OrgOrderQty, SaleUnit, MRP, PurchasePrice, TotalStock, SLSQty,
    UnitDescription, WantedType, ProductTypeName, Remarks, IsOffer,
    Qtycheck, Status, OrSupplier/Code) plus the supplier-match columns
    (SupplierProductCode/Name) assigned_orders joins in via
    SupplierProductMatch/SupplierStock."""
    sql = (
        "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.OrgOrderQty, om.SaleUnit, "
        "om.MRP, om.PurchasePrice, om.TotalStock, om.SLSQty, om.UnitDescription, "
        "om.WantedType, om.ProductTypeName, om.Remarks, om.IsOffer, om.Qtycheck, "
        "om.Status, om.OrSupplier, om.OrSupplierCode, "
        "SPM.SupplierProductCode, SS.SupplierProductName "
        "FROM OrderManagement om "
        "OUTER APPLY (SELECT TOP 1 SPM.SupplierProductCode, SPM.SupplierCode "
        "  FROM SupplierProductMatch SPM "
        "  WHERE SPM.ProductCode = om.ProductCode AND SPM.StoreName = om.StoreName "
        "    AND SPM.SupplierCode = om.OrSupplierCode) SPM "
        "LEFT JOIN SupplierStock SS ON SS.SupplierProductCode = SPM.SupplierProductCode "
        "  AND SS.SupplierCode = SPM.SupplierCode AND SS.StoreName = om.StoreName "
        "WHERE om.StoreName = ?"
    )
    cur = central_cur.execute(sql, store_name)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_product_history(central_cur, store_name, product_codes, top_n=5):
    """TOP 5 OrderManagementBackup rows per product -- same query as
    repository.qty_check_order_history, TOP 5 instead of TOP 25 (plan doc
    3.3: "last 5 order history per product", not last 5 orders)."""
    out = {}
    sql = (
        f"SELECT TOP {top_n} Productcode, Orqty, OrgOrderQty, saleunit, MRP, "
        "remarks, Wanteddate, WantedType, Orsupplier "
        "FROM OrderManagementBackup WHERE Productcode = ? AND StoreName = ? "
        "ORDER BY Wanteddate DESC"
    )
    for code in product_codes:
        cur = central_cur.execute(sql, code, store_name)
        rows = cur.fetchall()
        out[code] = rows
    return out


def _json_value(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return None
    return value


def _code(value):
    """Canonical text product code -- float 9664.0 and int 9664 are one code."""
    from modules.procurement.product_identity import canonical_product_code
    return canonical_product_code(value)


# Same projection as repository._WORKSPACE_COLS + IsOffer, every status: the
# store PC filters open lines itself after overlaying live line states.
_WORKSPACE_SQL = (
    "SELECT om.ProductCode, om.ProductName, om.OrderQty, om.OrgOrderQty, om.TotalStock, om.SLSQty, "
    "om.UnitDescription, om.SaleUnit, om.MRP, om.WantedType, om.Remarks, "
    "om.PurchasePrice, om.SubLocation, om.ProductTypeName, om.MaxQty, om.Status, "
    "om.Qtycheck, om.IsOffer "
    "FROM OrderManagement om WHERE om.StoreName = ?"
)

# Set-based twin of repository._LAST_OFFER_PATTERN_APPLY: per product, the most
# recent GRN (lines summed per Grnnumber) that carried free qty. One pass over
# the store's PurchaseTrans instead of an OUTER APPLY per order line.
_LAST_OFFER_SQL = (
    "SELECT x.ProductCode, x.base_qty, x.free_qty FROM ("
    "  SELECT g.ProductCode, g.base_qty, g.free_qty, "
    "  ROW_NUMBER() OVER (PARTITION BY g.ProductCode ORDER BY g.grn_date DESC) AS rn "
    "  FROM ("
    "    SELECT pt.ProductCode, pt.Grnnumber, SUM(pt.StockReceived) AS base_qty, "
    "    SUM(pt.FreeQty) AS free_qty, MAX(pt.GRNDate) AS grn_date "
    "    FROM PurchaseTrans pt WITH (NOLOCK) "
    "    WHERE pt.StoreName = ? AND pt.InvoiceSeries <> 'TI' "
    "    AND pt.ProductCode IN (SELECT CAST(om.ProductCode AS INT) FROM OrderManagement om WHERE om.StoreName = ?) "
    "    GROUP BY pt.ProductCode, pt.Grnnumber HAVING SUM(pt.FreeQty) > 0"
    "  ) g"
    ") x WHERE x.rn = 1"
)

# repository.orders_by_supplier's history EXISTS, flattened to (product,
# supplier) pairs once per build.
_PRODUCT_SUPPLIERS_SQL = (
    "SELECT DISTINCT pt.ProductCode, LTRIM(RTRIM(CAST(pt.SupplierCode AS VARCHAR(50)))) "
    "FROM PurchaseTrans pt WITH (NOLOCK) "
    "WHERE pt.StoreName = ? AND pt.InvoiceSeries <> 'TI' "
    "AND pt.ProductCode IN (SELECT CAST(om.ProductCode AS INT) FROM OrderManagement om WHERE om.StoreName = ?)"
)

# repository.supplier_stock_compare without the open-line filter (status is
# overlaid live on the PC), plus SupplierProductCode and the raw discount text
# Live Stock mode shows.
_SUPPLIER_STOCK_SQL = (
    "SELECT x.ProductCode, x.SupplierCode, x.SupplierProductName, x.SupplierProductCode, x.Stock, "
    "x.Discount, x.Sch, x.Free, x.MinQty, x.MRP, x.PTR, x.Rack, x.TransactionDate, "
    "(SELECT TOP 1 os.SupplierNAME FROM OrderSuppliers os "
    "  WHERE os.suppliercode = x.SupplierCode AND os.storename = ?) AS SupplierName "
    "FROM ("
    "  SELECT CAST(om.ProductCode AS INT) AS ProductCode, SS.SupplierCode, SS.SupplierProductName, "
    "  SS.SupplierProductCode, SS.Stock, SS.discound AS Discount, SS.sch AS Sch, SS.free AS Free, "
    "  SS.MINQTY AS MinQty, SS.mrp AS MRP, SS.ptr AS PTR, ISNULL(SS.Rack, '') AS Rack, "
    "  SS.transactiondate AS TransactionDate, "
    "  ROW_NUMBER() OVER (PARTITION BY om.ProductCode, SS.SupplierCode ORDER BY SS.Stock DESC) AS rn "
    "  FROM OrderManagement om "
    "  JOIN SupplierStock SS ON SS.StoreProductCode = CAST(CAST(om.ProductCode AS BIGINT) AS VARCHAR(50)) "
    "    AND SS.storename = om.StoreName "
    "  WHERE om.StoreName = ?"
    ") x WHERE x.rn = 1"
)


def _fetch_workspace_rows(central_cur, store_name):
    from modules.procurement.product_identity import collapse_lines
    cur = central_cur.execute(_WORKSPACE_SQL, store_name)
    cols = [d[0] for d in cur.description]
    rows = [{c: _json_value(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
    offers = {
        _code(r[0]): (_json_value(r[1]), _json_value(r[2]))
        for r in central_cur.execute(_LAST_OFFER_SQL, store_name, store_name).fetchall()
    }
    for row in rows:
        base, free = offers.get(_code(row["ProductCode"]), (None, None))
        row["LastOfferBaseQty"] = base
        row["LastOfferFreeQty"] = free
    return collapse_lines(rows)


def _fetch_product_suppliers(central_cur, store_name):
    pairs = set()
    for code, supplier in central_cur.execute(_PRODUCT_SUPPLIERS_SQL, store_name, store_name).fetchall():
        supplier = str(supplier or "").strip()
        if supplier:
            pairs.add((_code(code), supplier))
    return pairs


def supplier_stock_signature(central_cur, store_name):
    """Changes whenever an import replaces this store's SupplierStock: every
    writer (Excel/mail import, website harvest, legacy import) stamps
    transactiondate = GETDATE() on the rows it inserts."""
    row = central_cur.execute(
        "SELECT COUNT(*), MAX(transactiondate) FROM SupplierStock WHERE storename = ?", store_name
    ).fetchone()
    return f"{row[0]}|{_json_value(row[1])}"


def _fetch_supplier_stock(central_cur, store_name):
    lines = []
    for r in central_cur.execute(_SUPPLIER_STOCK_SQL, store_name, store_name).fetchall():
        raw_disc = r.Discount
        try:
            disc = float(str(raw_disc or "0").strip() or 0)
        except ValueError:
            disc = 0.0
        supplier = str(r.SupplierCode or "").strip()
        lines.append((_code(r.ProductCode), supplier, {
            "supplier_code": supplier,
            "supplier_name": (r.SupplierName or "").strip() or None,
            "supplier_product_name": (r.SupplierProductName or "").strip() or None,
            "supplier_product_code": _json_value(r.SupplierProductCode),
            "stock": float(r.Stock or 0),
            "discount": disc,
            "discount_raw": _json_value(raw_disc),
            "sch": int(r.Sch or 0),
            "free": int(r.Free or 0),
            "min_qty": int(r.MinQty or 0) or None,
            "mrp": float(r.MRP) if r.MRP is not None else None,
            "ptr": float(r.PTR) if r.PTR is not None else None,
            "rack": (r.Rack or "").strip() or None,
            "updated_at": _json_value(r.TransactionDate),
        }))
    return lines


def _stamp(cur, key, value):
    cur.execute("INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)", (key, value))


def _write_supplier_stock(cur, lines, signature):
    cur.execute("DELETE FROM supplier_stock")
    cur.executemany(
        "INSERT OR REPLACE INTO supplier_stock (product_code, supplier_code, line_json) VALUES (?, ?, ?)",
        [(code, supplier, json.dumps(line)) for code, supplier, line in lines],
    )
    _stamp(cur, "supplier_stock_sig", signature)
    _stamp(cur, "supplier_stock_at", datetime.datetime.now().isoformat())


def refresh_supplier_stock(store_name):
    """Re-reads only the supplier_stock table of an existing cache file when
    SupplierStock changed after it was written (a supplier's stock imported
    after the order was generated). Returns True when the file was updated;
    no-op when there is no cache file or nothing changed."""
    path = cache_path(store_name)
    with store_lock(store_name):
        if not os.path.exists(path):
            return False
        conn = sqlite3.connect(path, timeout=30)
        try:
            row = conn.execute("SELECT value FROM cache_meta WHERE key = 'supplier_stock_sig'").fetchone()
            current = row[0] if row else None
            with database.get_central_connection() as central:
                ccur = central.cursor()
                signature = supplier_stock_signature(ccur, store_name)
                if signature == current:
                    return False
                lines = _fetch_supplier_stock(ccur, store_name)
            schema.init_db(conn)
            cur = conn.cursor()
            _write_supplier_stock(cur, lines, signature)
            conn.commit()
            return True
        finally:
            conn.close()


def _ho_code(central_cur, store_name):
    """Stores.Ho_code: Live Stock flags the warehouse pseudo-supplier's rows
    (repository.orders_by_supplier is_warehouse_stock)."""
    try:
        row = central_cur.execute("SELECT Ho_code FROM Stores WHERE StoreName = ?", store_name).fetchone()
    except Exception:
        return None
    return str(row[0]).strip() if row and row[0] is not None else None


def _write_cache_file(path, store_name, order_lines, history_by_product, extras=None):
    conn = sqlite3.connect(path, timeout=30)
    try:
        schema.init_db(conn)
        cur = conn.cursor()
        now = datetime.datetime.now().isoformat()
        cur.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('store_name', ?)",
            (store_name,),
        )
        cur.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('built_at', ?)",
            (now,),
        )
        cur.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('schema_version', ?)",
            (str(schema.SCHEMA_VERSION),),
        )
        for row in order_lines:
            cur.execute(
                "INSERT OR REPLACE INTO order_lines ("
                "product_code, product_name, order_qty, org_order_qty, sale_unit, mrp, "
                "purchase_price, total_stock, sls_qty, unit_description, wanted_type, "
                "product_type_name, remarks, is_offer, qty_check, status, or_supplier, "
                "or_supplier_code, supplier_product_code, supplier_product_name) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["ProductCode"], row["ProductName"], row["OrderQty"], row["OrgOrderQty"],
                    row["SaleUnit"], row["MRP"], row["PurchasePrice"], row["TotalStock"],
                    row["SLSQty"], row["UnitDescription"], row["WantedType"],
                    row["ProductTypeName"], row["Remarks"], int(bool(row["IsOffer"])),
                    int(bool(row["Qtycheck"])), row["Status"], row["OrSupplier"],
                    row["OrSupplierCode"], row["SupplierProductCode"], row["SupplierProductName"],
                ),
            )
            cur.execute(
                "INSERT OR REPLACE INTO export_state (product_code, exported) VALUES (?, 0)",
                (row["ProductCode"],),
            )
        for product_code, history_rows in history_by_product.items():
            for rank, hrow in enumerate(history_rows, start=1):
                cur.execute(
                    "INSERT OR REPLACE INTO product_history ("
                    "product_code, rank, or_qty, org_order_qty, sale_unit, mrp, remarks, "
                    "wanted_date, wanted_type, or_supplier) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        product_code, rank, hrow.Orqty, hrow.OrgOrderQty, hrow.saleunit,
                        hrow.MRP, hrow.remarks, str(hrow.Wanteddate), hrow.WantedType,
                        hrow.Orsupplier,
                    ),
                )
        if extras:
            cur.executemany(
                "INSERT OR REPLACE INTO workspace_rows (product_code, row_json) VALUES (?, ?)",
                [(_code(r["ProductCode"]), json.dumps(r)) for r in extras["workspace_rows"]],
            )
            cur.executemany(
                "INSERT OR REPLACE INTO product_suppliers (product_code, supplier_code) VALUES (?, ?)",
                sorted(extras["product_suppliers"]),
            )
            _write_supplier_stock(cur, extras["supplier_stock"], extras["supplier_stock_sig"])
            if extras.get("ho_code"):
                _stamp(cur, "ho_code", extras["ho_code"])
        conn.commit()
    finally:
        conn.close()


def build_cache_for_store(store_name):
    """Builds a fresh cache for the store's CURRENT order, drains any
    pending write-back on the existing file first, then atomically replaces
    it. Returns the final cache_path. Safe to call even if no cache exists
    yet (first run for that store)."""
    final_path = cache_path(store_name)

    if os.path.exists(final_path):
        drained = writeback.drain(final_path)
        if not drained["ok"]:
            raise RuntimeError(
                f"Cannot replace order cache for '{store_name}': pending write-back "
                f"did not drain cleanly ({drained.get('error')}). Old cache file left in place."
            )

    with database.get_central_connection() as conn:
        cur = conn.cursor()
        order_lines = _fetch_current_order(cur, store_name)
        product_codes = [row["ProductCode"] for row in order_lines]
        history_by_product = _fetch_product_history(cur, store_name, product_codes)
        extras = {
            "workspace_rows": _fetch_workspace_rows(cur, store_name),
            "product_suppliers": _fetch_product_suppliers(cur, store_name),
            "supplier_stock_sig": supplier_stock_signature(cur, store_name),
            "supplier_stock": _fetch_supplier_stock(cur, store_name),
            "ho_code": _ho_code(cur, store_name),
        }

    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite", dir=os.path.dirname(final_path) or ".")
    os.close(fd)
    os.remove(tmp_path)
    try:
        _write_cache_file(tmp_path, store_name, order_lines, history_by_product, extras)
        with store_lock(store_name):
            if os.path.exists(final_path):
                os.remove(final_path)
            os.replace(tmp_path, final_path)
    except Exception:
        logger.exception("order cache build failed for %s", store_name)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return final_path
