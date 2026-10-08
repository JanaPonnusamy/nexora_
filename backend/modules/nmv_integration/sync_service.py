"""Sync mechanics for the NMV boundary.

Uplink reuses the Legacy module's MERGE dialect verbatim
(sync_engine.merge_keys / build_merge_sql) so an agent-posted row lands exactly
as the old direct branch pull would have -- there is no second merge semantics.
The only thing that differs is the transport: JSON over HTTPS instead of a
pyodbc read straight off the branch SQL Server.

Downlink reads are StoreName-scoped, offset-paginated entity pages.
"""
from __future__ import annotations

import datetime
import uuid

from modules.legacy_order import sync_engine
from modules.nmv_integration import repository, serializer
from modules.nmv_integration.exceptions import UnknownEntity

# source table -> OrderNMC destination (identical to the legacy pull plan;
# Suppliers deliberately lands in OrderSuppliers).
_SRC_TO_DEST = dict(sync_engine.TABLE_PLAN)

# How each uplink table's watermark is interpreted. Mirrors sync_engine's
# per-table watermarking; the agent and HO must agree on this.
UPLINK_STRATEGY = {
    "Products": "snapshot",
    "SaleInformation": "psi_minus_1000",
    "ProductTrans": "snapshot",
    "PurchaseTrans": "id",
    "ProductSaleInformation": "id",
    "SalesRep": "snapshot",
    "Suppliers": "snapshot",
    "Batches": "snapshot_replace",
    "SupplierProductMatch": "snapshot",
}

# Downlink entities: logical name -> (table, stable ORDER BY). All are
# StoreName-scoped. OrderManagement also has a dedicated /orders path.
_DOWNLINK_ENTITIES = {
    "OrderManagement": ("OrderManagement", "OrderId, ProductCode"),
    "OrderManagementBackup": ("OrderManagementBackup", "OrderId, ProductCode"),
    "OrderHeaderDetails": ("OrderHeaderDetails", "OrderId"),
    "OrderSuppliers": ("OrderSuppliers", "SupplierNAME"),
    "SupplierStock": ("SupplierStock", "suppliercode, supplierproductcode"),
    "SupplierProductMatch": ("SupplierProductMatch", "suppliercode, supplierproductcode"),
}

_STAMP_COLUMNS = ("StoreName", "Sync", "SyncDateTime")
_STRING_TYPES = {"char", "nchar", "varchar", "nvarchar", "text", "ntext"}


def dest_table_for(source_table):
    dest = _SRC_TO_DEST.get(source_table)
    if not dest:
        raise UnknownEntity(f"'{source_table}' is not a syncable NMV table.")
    return dest


def downlink_entities():
    return list(_DOWNLINK_ENTITIES)


# ---- uplink ---------------------------------------------------------------

def apply_uplink(cur, source_table, columns, rows, store_name, snapshot_reset=False):
    """Stage + MERGE one batch of agent rows into OrderNMC.

    Runs entirely on the caller's cursor/transaction (so it commits atomically
    with the message ledger). Returns (rows_applied, dropped_columns).
    """
    dest_table = dest_table_for(source_table)

    # Validate requested columns against the real destination; silently drop
    # anything the dest doesn't have so a malformed/extra column can't inject
    # into the staging DDL or MERGE.
    col_types = repository.dest_column_types(cur, dest_table, columns)
    known = [c for c in columns if col_types.get(c)]
    dropped = [c for c in columns if not col_types.get(c)]
    if not known:
        raise UnknownEntity(f"No known columns for destination '{dest_table}'.")

    stamp_types = repository.dest_column_types(cur, dest_table, list(_STAMP_COLUMNS))
    stamp_present = [c for c in _STAMP_COLUMNS if stamp_types.get(c)]
    all_cols = known + stamp_present
    all_types = dict(col_types)
    all_types.update({c: stamp_types[c] for c in stamp_present})

    # Batches is a full-snapshot replace: zero the store's stock before the
    # first page merges so sold-out batches don't keep stale stock forever
    # (identical to sync_engine's Batches handling).
    if snapshot_reset and dest_table.lower() == "batches":
        cur.execute("UPDATE Batches SET Stock = 0 WHERE StoreName = ?", store_name)

    if not rows:
        return 0, dropped

    stage = f"nmv_stage_{uuid.uuid4().hex[:8]}"
    col_defs = ", ".join(f"[{c}] {_sql_decl(all_types[c])}" for c in all_cols)
    cur.execute(f"CREATE TABLE [{stage}] ({col_defs})")
    try:
        now = datetime.datetime.now()
        stamp_values = {"StoreName": store_name, "Sync": 0, "SyncDateTime": now}
        payload = []
        for r in rows:
            vals = [
                serializer.coerce_inbound(r.get(c), all_types[c]["data_type"])
                for c in known
            ]
            vals.extend(stamp_values[c] for c in stamp_present)
            payload.append(tuple(vals))

        placeholders = ", ".join("?" for _ in all_cols)
        insert_cols = ", ".join(f"[{c}]" for c in all_cols)
        try:
            cur.fast_executemany = True
        except Exception:
            pass
        cur.executemany(
            f"INSERT INTO [{stage}] ({insert_cols}) VALUES ({placeholders})", payload
        )
        try:
            cur.fast_executemany = False
        except Exception:
            pass

        string_cols = {
            c for c in all_cols
            if (all_types[c] or {}).get("data_type") in _STRING_TYPES
        }
        cur.execute(sync_engine.build_merge_sql(dest_table, stage, all_cols, string_cols))
    finally:
        cur.execute(f"IF OBJECT_ID('{stage}', 'U') IS NOT NULL DROP TABLE [{stage}];")

    return len(rows), dropped


def _sql_decl(info):
    """Render an INFORMATION_SCHEMA column descriptor as a staging DDL type."""
    dt = (info or {}).get("data_type", "nvarchar")
    if dt in ("nvarchar", "varchar", "nchar", "char"):
        n = info.get("char_len")
        size = "MAX" if (n is None or n < 0) else str(n)
        return f"{dt.upper()}({size})"
    if dt in ("decimal", "numeric"):
        return f"{dt.upper()}({info.get('precision') or 18},{info.get('scale') or 0})"
    return dt.upper()


# ---- downlink -------------------------------------------------------------

def read_entity_page(cur, store_name, entity, cursor, limit):
    """One StoreName-scoped page of a downlink entity. Returns
    (rows, next_cursor, has_more)."""
    spec = _DOWNLINK_ENTITIES.get(entity)
    if not spec:
        raise UnknownEntity(f"'{entity}' is not a downlink entity.")
    table, order_by = spec
    offset = _safe_offset(cursor)
    limit = max(1, min(int(limit), 5000))

    cur.execute(
        f"SELECT * FROM [{table}] WHERE StoreName = ? "
        f"ORDER BY {order_by} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        store_name, offset, limit + 1,
    )
    rows = serializer.rows_to_dicts(cur)
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = str(offset + limit) if has_more else None
    return rows, next_cursor, has_more


def read_order(cur, store_name, order_id):
    """All OrderManagement rows for one order (the /orders path)."""
    cur.execute(
        "SELECT * FROM OrderManagement WHERE StoreName = ? AND OrderId = ? "
        "ORDER BY ProductCode",
        store_name, order_id,
    )
    return serializer.rows_to_dicts(cur)


def _safe_offset(cursor):
    try:
        return max(0, int(cursor))
    except (TypeError, ValueError):
        return 0
