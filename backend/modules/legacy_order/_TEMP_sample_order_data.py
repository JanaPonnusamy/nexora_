"""TEMPORARY sample-data fixture — DEVELOPMENT / SAMPLE DATA ONLY.

Delete this file once `.73` (192.168.10.73, OrderNMC + NEXORA_PLATFORM) is
confirmed back online and re-authorized for use. Created 2026-10-19 during
a planned ~22:20 IST outage window so Qty Check / Auto Purchase Update /
Supplier Stock could keep being exercised without a live connection.

Every row below is invented for this fixture. None of it is copied from a
real store, real supplier, or real product. Do not treat any value here as
representative of real stock, pricing, or sales.

Reuses the existing `_FakeConnection`/`monkeypatch` convention from
tests/test_legacy_order_workflow.py instead of introducing sqlite or a new
mock framework. Read-only: only exercises qty_check_rows and
orders_by_supplier (both pure SELECT in production). Never touches
update_order_qty, assign_supplier, bulk_assign_rows, order_process, or any
portal/export/WhatsApp path, so this cannot submit a real order.

Run directly to print the row shapes the three loaders return:

    backend/.venv/Scripts/python.exe backend/modules/legacy_order/_TEMP_sample_order_data.py
"""
from __future__ import annotations

import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.legacy_order import repository  # noqa: E402

SAMPLE_STORE = "DEV-SAMPLE-STORE"
SAMPLE_SUPPLIER_CODE = "DEV-SUP-001"
SAMPLE_HO_CODE = "94"  # matches the NMS/NMA-style Ho_code convention, not a real code

# -- OrderManagement sample rows (qty_check_rows: WHERE qtycheck=0 AND status=0) --
_QTY_CHECK_OM_ROWS = [
    # productcode, productname, orderqty, orgorderqty, totalstock, saleunit,
    # unitdescription, slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty,
    # Transactiondate, wantedtype, producttypename, remarks, IsOffer,
    # LastOfferBaseQty, LastOfferFreeQty
    (1001.0, "Sample Paracetamol 500mg", 5, 5, 12, 10, "Strip", 180, 25.0,
     "2026-09-20", "2026-10-15", 80, "2026-10-10", "Regular Order Based Min & Max",
     "Pharma", None, 1, 9, 1),
    (1002.0, "Sample Cough Syrup 100ml", 1, 1, 1, 1, "Bottle", 4, 60.0,
     "2026-08-01", "2026-10-05", 2, "2026-09-28", "Additional Row",
     "Pharma", "Additional", 0, None, None),
    (1003.0, "Sample Vitamin C Tablet", 0, 2, 40, 10, "Strip", 90, 15.0,
     "2026-09-01", "2026-09-30", 30, "2026-09-25", "Min & Max Based MaxsaleQTY",
     "Pharma", "No Need - Reviewed", 0, None, None),
]
_QTY_CHECK_COLS = [
    "productcode", "productname", "orderqty", "orgorderqty", "totalstock", "saleunit",
    "unitdescription", "slsqty", "mrp", "lastreceiveddate", "lastsaledate", "maxsaleqty",
    "Transactiondate", "wantedtype", "producttypename", "remarks", "IsOffer",
    "LastOfferBaseQty", "LastOfferFreeQty",
]

# -- orders_by_supplier(mode="history") sample rows --
_HISTORY_COLS = [
    "ProductCode", "ProductName", "OrderQty", "OrgOrderQty", "TotalStock", "SLSQty",
    "UnitDescription", "SaleUnit", "MRP", "WantedType", "Remarks", "PurchasePrice",
    "SubLocation", "ProductTypeName", "MaxQty", "Status", "Qtycheck", "IsOffer",
]
_HISTORY_ROWS = [
    (1001.0, "Sample Paracetamol 500mg", 5, 5, 12, 180, "Strip", 10, 25.0,
     "Regular Order Based Min & Max", None, 18.0, "A1-12", "Pharma", 18, 0, 0, 1),
]

# -- orders_by_supplier(mode="stock") sample rows --
_STOCK_COLS = [
    "ProductCode", "ProductName", "OrderQty", "OrgOrderQty", "TotalStock", "SLSQty",
    "UnitDescription", "SaleUnit", "MRP", "WantedType", "Remarks", "PurchasePrice",
    "SubLocation", "ProductTypeName", "MaxQty", "Status",
    "S_Stock", "Discount", "MinQty", "Sch", "Free", "SupplierProductName",
    "SupplierProductCode", "Rack", "IsOffer",
]
_STOCK_ROWS = [
    (1001.0, "Sample Paracetamol 500mg", 5, 5, 12, 180, "Strip", 10, 25.0,
     "Regular Order Based Min & Max", None, 18.0, "A1-12", "Pharma", 18, 0,
     120, 5.0, 10, "SCH10", 1, "Sample Supplier Paracetamol 500", "SP-1001", "R12", 1),
]


class _FakeCursor:
    def __init__(self, rows, cols):
        self._rows = rows
        self.description = [(c,) for c in cols]

    def execute(self, _sql, *_params):
        return self

    def fetchall(self):
        return self._rows


class _FakeConnection:
    """Mirrors tests/test_legacy_order_workflow.py's _FakeConnection shape."""

    def __init__(self, rows, cols):
        self._rows = rows
        self._cols = cols

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return _FakeCursor(self._rows, self._cols)


def run_qty_check_sample():
    """Exercises repository.qty_check_rows against sample OrderManagement rows."""
    import unittest.mock as mock

    fake = _FakeConnection(_QTY_CHECK_OM_ROWS, _QTY_CHECK_COLS)
    with mock.patch.object(repository.database, "get_central_connection", return_value=fake):
        return repository.qty_check_rows(SAMPLE_STORE)


def run_history_sample():
    """Exercises orders_by_supplier(mode='history') against sample rows."""
    import unittest.mock as mock

    fake = _FakeConnection(_HISTORY_ROWS, _HISTORY_COLS)
    with mock.patch.object(repository.database, "get_central_connection", return_value=fake):
        return repository.orders_by_supplier(SAMPLE_STORE, SAMPLE_SUPPLIER_CODE, "history")


def run_stock_sample():
    """Exercises orders_by_supplier(mode='stock') against sample rows.

    mode='stock' also calls repository.get_store() afterwards (to compute
    is_warehouse_stock), which does its own separate query shape
    (row-attribute access, not a plain tuple) -- mock that call directly
    rather than simulating a second cursor shape in _FakeCursor.
    """
    import unittest.mock as mock

    fake = _FakeConnection(_STOCK_ROWS, _STOCK_COLS)
    sample_store_record = {"store_name": SAMPLE_STORE, "ho_code": SAMPLE_HO_CODE}
    with mock.patch.object(repository.database, "get_central_connection", return_value=fake), \
         mock.patch.object(repository, "get_store", return_value=sample_store_record):
        rows = repository.orders_by_supplier(SAMPLE_STORE, SAMPLE_HO_CODE, "stock")
    return rows


if __name__ == "__main__":
    print("=== DEVELOPMENT / SAMPLE DATA — not a real store, not a real order ===\n")
    print("Qty Check sample rows (qty_check_rows):")
    for row in run_qty_check_sample():
        print(" ", row)
    print("\nAuto Purchase Update sample rows (orders_by_supplier mode=history):")
    for row in run_history_sample():
        print(" ", row)
    print("\nSupplier Stock sample rows (orders_by_supplier mode=stock):")
    for row in run_stock_sample():
        print(" ", row, "is_warehouse_stock=", row.get("is_warehouse_stock"))
