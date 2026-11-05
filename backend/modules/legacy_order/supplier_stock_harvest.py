"""Harvest a portal supplier's live stock into dbo.SupplierStock.

Owner 2026-11-05 — ONE job only: the Stock Client reads a supplier's whole
portal catalog headlessly (its own rendered product list with stock) and POSTs
it here; we replace that supplier+store's SupplierStock rows with the snapshot.

Nothing else happens here. Matching the supplier's products to the store's
products, and loading them into the order grid, are separate concerns:

  * the existing **Live Stock** By Supplier mode (repository.orders_by_supplier,
    mode='stock') already joins OrderManagement -> SupplierProductMatch ->
    SupplierStock, so once this fills SupplierStock the stock shows in the grid
    with no new compare code; and
  * **supplier_match_review.py** handles the products that are not mapped yet
    (fuzzy-suggest + manual map into SupplierProductMatch).

No credentials or site sessions live here — the headless login + read happen on
the store PC (the Stock Client), which holds the encrypted login. This module
only stores the stock it is handed.
"""
from __future__ import annotations

import datetime as _dt

from modules.legacy_order import database

# SupplierStock columns we write (the legacy table Live Stock + the compare card
# already read).
_STOCK_COLS = (
    "suppliercode", "supplierproductcode", "supplierproductname", "mrp", "ptr",
    "stock", "discound", "packing", "storename", "sch", "free", "transactiondate",
)


def _store(store_name):
    store = str(store_name or "").strip()
    if not store or len(store) > 50:
        raise ValueError("Pick a store first.")
    return store


def _supplier(supplier_code):
    code = str(supplier_code or "").strip()
    if not code or len(code) > 200:
        raise ValueError("Pick a supplier first.")
    return code


def _num(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _int(value):
    n = _num(value)
    return int(n) if n is not None else None


def replace_supplier_stock(conn, store, supplier_code, rows):
    """Replace this supplier+store's SupplierStock with the harvested snapshot.
    Returns the number of rows written."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM dbo.SupplierStock WHERE suppliercode = ? AND storename = ?",
        supplier_code, store,
    )
    today = _dt.date.today()
    placeholders = ", ".join("?" for _ in _STOCK_COLS)
    prepared = []
    for r in rows:
        name = " ".join(str(r.get("name") or "").split())
        if not name:
            continue
        prepared.append((
            supplier_code,
            str(r.get("code") or "").strip()[:100] or None,
            name[:200],
            _num(r.get("mrp")),
            _num(r.get("ptr")),
            _int(r.get("stock")) or 0,
            _num(r.get("discount")),
            str(r.get("packing") or "").strip()[:100] or None,
            store,
            str(r.get("scheme") or "").strip()[:100] or None,
            _int(r.get("free")) or 0,
            today,
        ))
    if prepared:
        cur.executemany(
            f"INSERT INTO dbo.SupplierStock ({', '.join(_STOCK_COLS)}) "
            f"VALUES ({placeholders})",
            prepared,
        )
    return len(prepared)


def harvest(store_name, supplier_code, rows, actor=None):
    """Store the harvested catalog in SupplierStock. actor is accepted for a
    uniform signature; SupplierStock has no audit columns. Returns how many rows
    were stored and when."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    with database.get_central_connection() as conn:
        stored = replace_supplier_stock(conn, store, supplier, rows)
        conn.commit()
    return {"stored": stored, "harvested_at": _dt.datetime.now().isoformat(timespec="seconds")}


def last_harvest(store_name, supplier_code):
    """When this supplier+store's SupplierStock was last written, and how many
    rows it holds -- so the UI can show freshness."""
    store, supplier = _store(store_name), _supplier(supplier_code)
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT COUNT(*), MAX(transactiondate) FROM dbo.SupplierStock "
            "WHERE suppliercode = ? AND storename = ?", supplier, store,
        ).fetchone()
    return {"rows": int(row[0] or 0), "harvested_at": row[1].isoformat() if row[1] else None}
