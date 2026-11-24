"""Read-only access to a store's local order cache file, for the view
endpoint. Design doc: Order_Sync_Redesign_Plan.md section 3.3.

Deliberately separate from builder.py/writeback.py: this never writes, so a
reader bug can't corrupt the cache -- it opens the file, selects, closes.
"""
import os
import sqlite3


def read_cache(store_name, cache_path_fn):
    """Returns the cache contents as plain dicts, or None if no cache file
    exists yet for this store (caller falls back to the live API)."""
    path = cache_path_fn(store_name)
    if not os.path.exists(path):
        return None

    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        meta = {row["key"]: row["value"] for row in cur.execute("SELECT key, value FROM cache_meta")}
        order_lines = [dict(row) for row in cur.execute(
            "SELECT * FROM order_lines ORDER BY product_name"
        )]
        history = {}
        for row in cur.execute("SELECT * FROM product_history ORDER BY product_code, rank"):
            history.setdefault(row["product_code"], []).append(dict(row))
        export_state = {row["product_code"]: dict(row) for row in cur.execute("SELECT * FROM export_state")}
        pending_count = cur.execute("SELECT COUNT(*) FROM pending_writeback").fetchone()[0]
        return {
            "meta": meta,
            "order_lines": order_lines,
            "product_history": history,
            "export_state": export_state,
            "pending_writeback_count": pending_count,
        }
    finally:
        conn.close()
