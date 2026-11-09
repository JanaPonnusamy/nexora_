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
        n = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    # A scraped "Available"/garbled figure can come through as inf/NaN; neither
    # fits the decimal/float columns, so treat it as unknown rather than 500.
    return n if n == n and abs(n) != float("inf") else None


def _int(value):
    n = _num(value)
    return int(n) if n is not None else None


def _prepare(store, supplier_code, rows):
    """Clean + shape the posted rows into SupplierStock tuples. Skips blanks.
    Every varchar column here is 50 chars wide (dbo.SupplierStock) -- truncate
    to that, not a guessed wider limit, or a long real product/scheme name
    overflows the column and the whole harvest 500s mid-insert."""
    today = _dt.date.today()
    prepared = []
    for r in rows:
        name = " ".join(str(r.get("name") or "").split())
        if not name:
            continue
        prepared.append((
            supplier_code[:50],
            str(r.get("code") or "").strip()[:50] or None,
            name[:50],
            _num(r.get("mrp")),
            _num(r.get("ptr")),
            _int(r.get("stock")) or 0,
            _num(r.get("discount")),
            str(r.get("packing") or "").strip()[:50] or None,
            store[:50],
            str(r.get("scheme") or "").strip()[:50] or None,
            _int(r.get("free")) or 0,
            today,
        ))
    return prepared


def harvest(store_name, supplier_code, rows, complete=True, actor=None):
    """Replace this supplier+store's SupplierStock with the harvested snapshot,
    ALL-OR-NOTHING: the DELETE + INSERT run in one transaction, so any failure
    rolls back and the OLD stock is kept untouched (owner rule 2026-11-05 --
    "if it breaks mid-way keep the old one and retry").

    `complete` must be True: the client only posts after it has read the WHOLE
    catalog, so a partial read never reaches here. A post with complete=False, or
    an empty catalog, is refused WITHOUT touching the existing stock -- a broken
    harvest must never wipe good stock. actor is accepted for a uniform
    signature (SupplierStock has no audit columns).
    """
    store, supplier = _store(store_name), _supplier(supplier_code)
    if not complete:
        raise ValueError("Harvest was not complete — keeping the existing stock.")
    prepared = _prepare(store, supplier, rows)
    if not prepared:
        raise ValueError("No products were read — keeping the existing stock.")
    placeholders = ", ".join("?" for _ in _STOCK_COLS)
    with database.get_central_connection() as conn:
        # One transaction: pyodbc opens it on the first statement and does not
        # autocommit, so the DELETE is only visible once the INSERT also
        # succeeds and we commit. Any error -> rollback -> old stock intact.
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM dbo.SupplierStock WHERE suppliercode = ? AND storename = ?",
                supplier, store,
            )
            cur.executemany(
                f"INSERT INTO dbo.SupplierStock ({', '.join(_STOCK_COLS)}) "
                f"VALUES ({placeholders})",
                prepared,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"stored": len(prepared), "harvested_at": _dt.datetime.now().isoformat(timespec="seconds")}


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
