"""Drains a cache file's pending_writeback table into central OrderNMC/
OrderSMS/OrderSuccess. Design doc: Order_Sync_Redesign_Plan.md section 3.3.

Central DB remains source of truth (owner-confirmed): every local edit
(qty change, assign/unassign, export) is written to pending_writeback
immediately by the app, then this drains it to central -- either on a
timer/on-demand from the app, or forced by builder.py right before the
cache file is replaced for the next order.
"""
import logging
import sqlite3

from .. import database

logger = logging.getLogger(__name__)

# field -> (central column, value coercion). Kept narrow and explicit --
# only fields Qty Check / Assign / Export actually write, not a generic
# "any column" writer, so a bad local field name fails loudly instead of
# silently writing into the wrong OrderManagement column.
_FIELD_TO_COLUMN = {
    "order_qty": ("OrderQty", float),
    "status": ("Status", int),
    "qty_check": ("Qtycheck", int),
    "or_supplier_code": ("OrSupplierCode", str),
}


def drain(cache_file_path):
    """Applies every pending_writeback row to central, oldest first, then
    clears them from the cache file. Returns {"ok": bool, "applied": n,
    "error": str|None}. Stops at the first failure (leaves it and everything
    after it in pending_writeback) so a partial drain is never silently
    treated as complete -- the caller (builder.build_cache_for_store) must
    refuse to replace the file when ok is False."""
    conn = sqlite3.connect(cache_file_path, timeout=30)
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, product_code, field, value FROM pending_writeback ORDER BY id"
        ).fetchall()
        if not rows:
            return {"ok": True, "applied": 0, "error": None}

        store_name = cur.execute(
            "SELECT value FROM cache_meta WHERE key = 'store_name'"
        ).fetchone()
        store_name = store_name[0] if store_name else None
        if not store_name:
            return {"ok": False, "applied": 0, "error": "cache file has no store_name in cache_meta"}

        applied = 0
        with database.get_central_connection() as central_conn:
            central_cur = central_conn.cursor()
            for row_id, product_code, field, value in rows:
                mapping = _FIELD_TO_COLUMN.get(field)
                if not mapping:
                    return {"ok": False, "applied": applied, "error": f"unknown write-back field '{field}'"}
                column, coerce = mapping
                try:
                    coerced = coerce(value)
                except (TypeError, ValueError) as exc:
                    return {"ok": False, "applied": applied, "error": f"bad value for {field}: {exc}"}
                central_cur.execute(
                    f"UPDATE OrderManagement SET [{column}] = ? WHERE StoreName = ? AND ProductCode = ?",
                    coerced, store_name, product_code,
                )
                cur.execute("DELETE FROM pending_writeback WHERE id = ?", (row_id,))
                applied += 1
            central_conn.commit()
        conn.commit()
        return {"ok": True, "applied": applied, "error": None}
    except Exception as exc:
        logger.exception("write-back drain failed for %s", cache_file_path)
        return {"ok": False, "applied": 0, "error": str(exc)}
    finally:
        conn.close()


def queue_write(cache_file_path, product_code, field, value):
    """App-side helper: records one pending local edit. Call this from the
    Qty Check/Assign/Export write paths once they're pointed at the local
    cache (not yet wired -- see plan doc 3.3's open items)."""
    if field not in _FIELD_TO_COLUMN:
        raise ValueError(f"Unsupported write-back field: {field}")
    conn = sqlite3.connect(cache_file_path, timeout=30)
    try:
        conn.execute(
            "INSERT INTO pending_writeback (product_code, field, value) VALUES (?, ?, ?)",
            (product_code, field, str(value)),
        )
        conn.commit()
    finally:
        conn.close()
