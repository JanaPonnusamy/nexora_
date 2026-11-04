"""Which source tables/columns are mirrored, their keys, and value encoding."""
from __future__ import annotations

import datetime
import decimal
import fnmatch
import os
import uuid

from modules.ordernmc_mirror.sql_builder import UNSUPPORTED_TYPES

# Nexora/agent infrastructure that lives in OrderNMC but is not legacy business
# data (and, for Users/roles/tenants, must never overwrite the remote PC's own
# rows). Everything else in dbo is mirrored. Extend with
# ORDERNMC_MIRROR_EXCLUDE_TABLES; force a default-excluded table back in with
# ORDERNMC_MIRROR_INCLUDE_TABLES (both comma-separated, * wildcards).
DEFAULT_EXCLUDED_TABLES = (
    "sync_*", "Sync*", "sysdiagrams", "nmv_*", "store_agents", "user_store_access",
    "Users", "roles", "tenants", "LegacyOrderProcessingLock", "*_Stage_*",
    "column_mapping*", "Products_DiscountBackup_*",
)

# Branch SQL logins stay on HO.
EXCLUDED_COLUMNS = {
    "stores": {"password", "encrypted_password"},
}

# Natural keys for tables without a PRIMARY KEY (same keys the legacy app and
# the skip rules use). A heap without an entry here is keyed on all columns.
HEAP_KEYS = {
    "ordermanagement": ["StoreName", "OrderId", "ProductCode"],
    "ordermanagementbackup": ["StoreName", "OrderId", "ProductCode"],
    "ordermanagementho": ["StoreName", "OrderId", "ProductCode"],
    "suppliers": ["suppliercode", "StoreName"],
}


def _patterns(env_name: str) -> list[str]:
    return [p.strip() for p in os.getenv(env_name, "").split(",") if p.strip()]


def _matches(name: str, patterns) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatchcase(low, p.lower()) for p in patterns)


def is_mirrored(name: str, whitelist: list[str] | None = None) -> bool:
    if whitelist:
        return _matches(name, whitelist)
    if _matches(name, _patterns("ORDERNMC_MIRROR_INCLUDE_TABLES")):
        return True
    excluded = list(DEFAULT_EXCLUDED_TABLES) + _patterns("ORDERNMC_MIRROR_EXCLUDE_TABLES")
    return not _matches(name, excluded)


# Column that scopes a row to one store. A store-scoped target (e.g. only the
# TESTSMS stores) mirrors just the tables that have it, and only those stores'
# rows; tables without it are skipped so no other tenant's data can leak.
STORE_COLUMN = "storename"
# Per-site store config (StoreCode numbering, branch logins): a store-scoped
# remote PC keeps its own copy.
STORE_SCOPED_EXCLUDED = {"stores"}


def list_tables(conn, whitelist: list[str] | None = None,
                store_scoped: bool = False) -> list[dict]:
    """Mirrored dbo tables with columns + key, ordered by name.

    Each: {"name", "object_id", "rows", "columns", "pk_columns", "key_columns",
    "mode", "store_column"} where mode is "upsert" (real PK) or "replace" (heap:
    rows grouped by the natural key are replaced as a group). With
    ``store_scoped`` only tables that have a StoreName column are returned."""
    cur = conn.cursor()
    cur.execute(
        "SELECT t.object_id, t.name, "
        "(SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = t.object_id AND p.index_id IN (0,1)) "
        "FROM sys.tables t WHERE t.schema_id = SCHEMA_ID('dbo') AND t.is_ms_shipped = 0 ORDER BY t.name"
    )
    tables = [{"object_id": r[0], "name": r[1], "rows": int(r[2] or 0)}
              for r in cur.fetchall() if is_mirrored(r[1], whitelist)]
    if not tables:
        return []
    ids = {t["object_id"]: t for t in tables}

    cur.execute(
        "SELECT c.object_id, c.name, TYPE_NAME(c.system_type_id), c.max_length, c.precision, "
        "c.scale, c.is_nullable, c.is_identity, c.is_computed "
        "FROM sys.columns c JOIN sys.tables t ON t.object_id = c.object_id "
        "WHERE t.schema_id = SCHEMA_ID('dbo') ORDER BY c.object_id, c.column_id"
    )
    cols = {}
    for r in cur.fetchall():
        if r[0] not in ids or r[8]:
            continue
        cols.setdefault(r[0], []).append({
            "name": r[1], "type": (r[2] or "").lower(), "max_length": r[3],
            "precision": r[4], "scale": r[5], "nullable": bool(r[6]),
            "identity": bool(r[7]),
        })

    cur.execute(
        "SELECT ic.object_id, c.name FROM sys.indexes i "
        "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
        "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
        "WHERE i.is_primary_key = 1 ORDER BY ic.object_id, ic.key_ordinal"
    )
    pks = {}
    for r in cur.fetchall():
        if r[0] in ids:
            pks.setdefault(r[0], []).append(r[1])

    out = []
    for t in tables:
        dropped = EXCLUDED_COLUMNS.get(t["name"].lower(), set())
        pk = pks.get(t["object_id"], [])
        tcols = [c for c in cols.get(t["object_id"], [])
                 if c["type"] not in UNSUPPORTED_TYPES
                 and (c["name"].lower() not in dropped or c["name"] in pk)]
        names = {c["name"].lower(): c["name"] for c in tcols}
        if pk and all(k.lower() in names for k in pk):
            key, mode = pk, "upsert"
        else:
            pk = []
            wanted = HEAP_KEYS.get(t["name"].lower())
            if wanted and all(k.lower() in names for k in wanted):
                key = [names[k.lower()] for k in wanted]
            else:
                key = [c["name"] for c in tcols]
            mode = "replace"
        if not tcols:
            continue
        store_column = names.get(STORE_COLUMN)
        if store_scoped and (not store_column or t["name"].lower() in STORE_SCOPED_EXCLUDED):
            continue
        out.append({**t, "columns": tcols, "pk_columns": pk, "key_columns": key,
                    "mode": mode, "store_column": store_column})
    return out


def last_user_updates(conn) -> dict | None:
    """{object_id: last write time} since SQL Server start, or None when it
    cannot be trusted: the login lacks VIEW SERVER STATE, or the database has
    AUTO_CLOSE on -- SQL Server drops a database's usage stats every time it
    auto-closes, so "no recorded write" would hide real changes (seen on the
    .32 OrderNMC: tables written minutes earlier had no stats at all)."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_auto_close_on FROM sys.databases WHERE database_id = DB_ID()")
        row = cur.fetchone()
        if row and row[0]:
            return None
        cur.execute(
            "SELECT object_id, MAX(last_user_update) FROM sys.dm_db_index_usage_stats "
            "WHERE database_id = DB_ID() GROUP BY object_id"
        )
        return {r[0]: r[1] for r in cur.fetchall()}
    except Exception:
        return None


# ---- value codec (shared contract with store_agent/ordernmc_mirror) ---------

def encode_value(value):
    """Python value from pyodbc -> JSON-safe value (types travel in metadata)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def decode_value(sql_type_name: str, value):
    """Inverse of encode_value for one column type."""
    if value is None:
        return None
    t = sql_type_name
    if t in ("datetime", "datetime2", "smalldatetime", "datetimeoffset"):
        return datetime.datetime.fromisoformat(value)
    if t == "date":
        return datetime.date.fromisoformat(value)
    if t == "time":
        return datetime.time.fromisoformat(value)
    if t in ("decimal", "numeric", "money", "smallmoney"):
        return decimal.Decimal(value)
    if t in ("binary", "varbinary"):
        return bytes.fromhex(value)
    return value
