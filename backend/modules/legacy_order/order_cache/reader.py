"""Read-only access to a store's local order cache file, for the view
endpoint. Design doc: Order_Sync_Redesign_Plan.md section 3.3.

Deliberately separate from builder.py/writeback.py: this never writes, so a
reader bug can't corrupt the cache -- it opens the file, selects, closes.
"""
import json
import os
import sqlite3


def stamp_of(meta):
    """What a store PC compares to decide whether to re-download: the order
    build plus the last supplier-stock refresh."""
    return f"{meta.get('built_at') or ''}|{meta.get('supplier_stock_at') or ''}"


def read_meta(store_name, cache_path_fn):
    path = cache_path_fn(store_name)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path, timeout=10)
    try:
        return {k: v for k, v in conn.execute("SELECT key, value FROM cache_meta")}
    finally:
        conn.close()


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
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        workspace_rows, product_suppliers, supplier_stock = [], {}, {}
        if "workspace_rows" in tables:
            workspace_rows = [json.loads(r[0]) for r in cur.execute("SELECT row_json FROM workspace_rows")]
            for code, supplier in cur.execute("SELECT product_code, supplier_code FROM product_suppliers"):
                product_suppliers.setdefault(code, []).append(supplier)
            for code, line in cur.execute("SELECT product_code, line_json FROM supplier_stock"):
                supplier_stock.setdefault(code, []).append(json.loads(line))
        return {
            "stamp": stamp_of(meta),
            "workspace_rows": workspace_rows,
            "product_suppliers": product_suppliers,
            "supplier_stock": supplier_stock,
            "meta": meta,
            "order_lines": order_lines,
            "product_history": history,
            "export_state": export_state,
            "pending_writeback_count": pending_count,
        }
    finally:
        conn.close()
