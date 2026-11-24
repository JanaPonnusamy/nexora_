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
import logging
import os
import sqlite3
import tempfile

from .. import database
from . import schema, writeback

logger = logging.getLogger(__name__)

CACHE_DIR_ENV = "NEXORA_ORDER_CACHE_DIR"


def cache_path(store_name):
    base = os.environ.get(CACHE_DIR_ENV) or os.path.join(
        os.environ.get("NEXORA_INSTALL_PATH", "."), "order_cache"
    )
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


def _write_cache_file(path, store_name, order_lines, history_by_product):
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

    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite", dir=os.path.dirname(final_path) or ".")
    os.close(fd)
    os.remove(tmp_path)
    try:
        _write_cache_file(tmp_path, store_name, order_lines, history_by_product)
        if os.path.exists(final_path):
            os.remove(final_path)
        os.replace(tmp_path, final_path)
    except Exception:
        logger.exception("order cache build failed for %s", store_name)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return final_path
