"""COSEC database extraction utility.

Connects READ-ONLY to the Matrix COSEC attendance SQL Server database
(backend/modules/time_report/database.py's server -- see backend/.env
COSEC_DB_* vars) and generates a single, self-contained .sql script that
recreates the schema (tables, PKs, unique/check/default constraints,
foreign keys, indexes) and populates it with a deterministic, capped
sample of data, suitable for spinning up a throwaway dev/test copy of
COSEC on any other SQL Server.

Only SELECT and metadata (sys.*) queries are ever issued against the
source database -- no INSERT/UPDATE/DELETE/ALTER/DROP/TRUNCATE.

Usage:
    python backend/scripts/cosec_db_extract.py [--output PATH]
        [--target-db NAME] [--max-rows N]

Design notes (why some choices deviate slightly from a naive reading of
the spec, and why that's still correct):

* Foreign keys are added via ``ALTER TABLE ... WITH NOCHECK ADD CONSTRAINT``
  *after* all sample data is loaded. Each table is independently sampled
  (TOP N, its own ORDER BY) so a child row's FK value is not guaranteed to
  point at a row that survived the parent's own TOP-N/IsActive sample --
  full cross-table referential closure is fundamentally incompatible with
  a hard 100-row-per-table cap. WITH NOCHECK is the standard, documented
  way to load independently-sampled data without the script aborting on
  an FK violation, while still leaving the constraint (and its metadata/
  name/actions) in place for anything inserted afterwards.
* The target database name is made configurable via a sqlcmd scripting
  variable (``:setvar TargetDatabaseName``) rather than a plain T-SQL
  ``DECLARE``, because a DECLARE'd variable does not survive a ``GO``
  batch separator and the rest of the script (USE, every CREATE/INSERT)
  needs the name across many batches. sqlcmd variables do survive across
  GO and are the standard mechanism SSMS/sqlcmd deployment scripts use for
  exactly this. Run the output with sqlcmd.exe, or SSMS with
  Query > SQLCMD Mode enabled.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import decimal
import os
import struct
import sys
from collections import defaultdict, deque
from pathlib import Path

import pyodbc

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

MAX_ROWS_DEFAULT = 100
_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"

# SQL types that cannot appear in ORDER BY / comparisons -- excluded from
# fallback deterministic ordering when no PK/unique key is available.
_NON_ORDERABLE_TYPES = {
    "text", "ntext", "image", "xml", "geography", "geometry",
    "hierarchyid", "sql_variant",
}

# Safety cap: a single binary literal larger than this is still emitted in
# full (never truncated/corrupted) but flagged with a preceding comment so
# the resulting file size growth is visible rather than silent.
LARGE_BINARY_WARN_BYTES = 2 * 1024 * 1024


# --------------------------------------------------------------------------
# Source connection (read-only)
# --------------------------------------------------------------------------

def _handle_datetimeoffset(raw):
    # ODBC SQL_SS_TIMESTAMPOFFSET_STRUCT: y,m,d,h,min,s,frac(uint32),tz_h,tz_m
    y, m, d, hh, mm, ss, frac, tz_h, tz_m = struct.unpack("<6hI2h", raw)
    sign = "+" if tz_h >= 0 else "-"
    return (
        f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}."
        f"{frac // 100:06d} {sign}{abs(tz_h):02d}:{abs(tz_m):02d}"
    )


def connect_source():
    server = os.getenv("COSEC_DB_SERVER")
    database = os.getenv("COSEC_DB_DATABASE", "COSEC")
    username = os.getenv("COSEC_DB_USERNAME")
    password = os.getenv("COSEC_DB_PASSWORD")
    driver = os.getenv("COSEC_DB_DRIVER", _DEFAULT_DRIVER)

    missing = [n for n, v in (
        ("COSEC_DB_SERVER", server),
        ("COSEC_DB_USERNAME", username),
        ("COSEC_DB_PASSWORD", password),
    ) if not v]
    if missing:
        raise RuntimeError(
            "Missing required env vars: " + ", ".join(missing)
            + ". Set them in backend/.env."
        )

    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={username};PWD={password};TrustServerCertificate=yes;"
    )
    conn = pyodbc.connect(conn_str, timeout=15)
    conn.add_output_converter(-155, _handle_datetimeoffset)  # SQL_SS_TIMESTAMPOFFSET
    conn.autocommit = False  # never matters -- we never write, but be explicit
    return conn


def quoted(name: str) -> str:
    """SQL Server bracket-quote an identifier. Doubles any embedded ']'."""
    return "[" + str(name).replace("]", "]]") + "]"


def qualified(schema: str, name: str) -> str:
    return f"{quoted(schema)}.{quoted(name)}"


# --------------------------------------------------------------------------
# Metadata model
# --------------------------------------------------------------------------

class Column:
    __slots__ = (
        "column_id", "name", "type_name", "max_length", "precision", "scale",
        "is_nullable", "is_identity", "is_computed", "computed_definition",
        "is_persisted", "seed_value", "increment_value", "is_rowversion",
    )

    def __init__(self, row):
        self.column_id = row.column_id
        self.name = row.column_name
        self.type_name = row.type_name
        self.max_length = row.max_length
        self.precision = row.precision
        self.scale = row.scale
        self.is_nullable = bool(row.is_nullable)
        self.is_identity = bool(row.is_identity)
        self.is_computed = bool(row.is_computed)
        self.computed_definition = row.computed_definition
        self.is_persisted = bool(row.is_persisted) if row.is_persisted is not None else False
        self.seed_value = row.seed_value
        self.increment_value = row.increment_value
        self.is_rowversion = row.type_name in ("timestamp", "rowversion")

    @property
    def is_insertable(self) -> bool:
        return not self.is_computed and not self.is_rowversion

    @property
    def is_orderable(self) -> bool:
        return self.type_name not in _NON_ORDERABLE_TYPES and not self.is_computed


class Table:
    def __init__(self, object_id, schema, name):
        self.object_id = object_id
        self.schema = schema
        self.name = name
        self.columns: list[Column] = []
        self.pk_name = None
        self.pk_columns: list[tuple[str, bool]] = []  # (col, is_descending)
        self.unique_constraints: list[dict] = []
        self.check_constraints: list[dict] = []
        self.default_constraints: list[dict] = []
        self.indexes: list[dict] = []
        self.outgoing_fks: list[dict] = []
        # populated during data extraction
        self.row_count_fetched = 0
        self.total_row_count = None
        self.is_active_column: Column | None = None
        self.order_by_columns: list[str] | None = None
        self.order_by_reason = ""

    @property
    def qualified_name(self) -> str:
        return qualified(self.schema, self.name)

    @property
    def display_name(self) -> str:
        return f"[{self.schema}].[{self.name}]"

    @property
    def insertable_columns(self) -> list[Column]:
        return [c for c in self.columns if c.is_insertable]

    @property
    def has_identity(self) -> bool:
        return any(c.is_identity for c in self.columns)


# --------------------------------------------------------------------------
# Metadata extraction (read-only sys.* catalog queries)
# --------------------------------------------------------------------------

def fetch_tables(conn) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.object_id, s.name AS schema_name, t.name AS table_name
        FROM sys.tables t
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE t.is_ms_shipped = 0 AND t.type = 'U'
        ORDER BY s.name, t.name
        """
    )
    tables = {}
    for row in cur.fetchall():
        tables[row.object_id] = Table(row.object_id, row.schema_name, row.table_name)
    return tables


def fetch_columns(conn, tables: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            c.object_id, c.column_id, c.name AS column_name,
            ty.name AS type_name, c.max_length, c.precision, c.scale,
            c.is_nullable, c.is_identity, c.is_computed,
            cc.definition AS computed_definition, cc.is_persisted,
            CAST(ic.seed_value AS bigint) AS seed_value,
            CAST(ic.increment_value AS bigint) AS increment_value
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        LEFT JOIN sys.computed_columns cc
            ON cc.object_id = c.object_id AND cc.column_id = c.column_id
        LEFT JOIN sys.identity_columns ic
            ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE t.is_ms_shipped = 0 AND t.type = 'U'
        ORDER BY c.object_id, c.column_id
        """
    )
    for row in cur.fetchall():
        table = tables.get(row.object_id)
        if table is None:
            continue
        table.columns.append(Column(row))


def fetch_primary_and_unique_keys(conn, tables: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            kc.parent_object_id AS table_object_id, kc.name AS constraint_name,
            kc.type AS constraint_type, ic.key_ordinal, col.name AS column_name,
            ic.is_descending_key
        FROM sys.key_constraints kc
        JOIN sys.index_columns ic
            ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
        JOIN sys.columns col ON col.object_id = ic.object_id AND col.column_id = ic.column_id
        JOIN sys.tables t ON t.object_id = kc.parent_object_id
        WHERE t.is_ms_shipped = 0
        ORDER BY kc.parent_object_id, kc.name, ic.key_ordinal
        """
    )
    grouped = defaultdict(list)
    for row in cur.fetchall():
        grouped[(row.table_object_id, row.constraint_name, row.constraint_type)].append(row)

    for (obj_id, cname, ctype), rows in grouped.items():
        table = tables.get(obj_id)
        if table is None:
            continue
        cols = [(r.column_name, bool(r.is_descending_key)) for r in rows]
        if ctype == "PK":
            table.pk_name = cname
            table.pk_columns = cols
        else:  # 'UQ'
            table.unique_constraints.append({"name": cname, "columns": cols})


def fetch_check_constraints(conn, tables: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cc.parent_object_id AS table_object_id, cc.name, cc.definition
        FROM sys.check_constraints cc
        JOIN sys.tables t ON t.object_id = cc.parent_object_id
        WHERE t.is_ms_shipped = 0
        ORDER BY cc.parent_object_id, cc.name
        """
    )
    for row in cur.fetchall():
        table = tables.get(row.table_object_id)
        if table is None:
            continue
        table.check_constraints.append({"name": row.name, "definition": row.definition})


def fetch_default_constraints(conn, tables: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT dc.parent_object_id AS table_object_id, col.name AS column_name,
               dc.name, dc.definition
        FROM sys.default_constraints dc
        JOIN sys.columns col ON col.object_id = dc.parent_object_id
            AND col.column_id = dc.parent_column_id
        JOIN sys.tables t ON t.object_id = dc.parent_object_id
        WHERE t.is_ms_shipped = 0
        ORDER BY dc.parent_object_id, dc.name
        """
    )
    for row in cur.fetchall():
        table = tables.get(row.table_object_id)
        if table is None:
            continue
        table.default_constraints.append(
            {"name": row.name, "column": row.column_name, "definition": row.definition}
        )


def fetch_indexes(conn, tables: dict) -> None:
    """Non-constraint-backed indexes only (PK/UNIQUE constraints are handled
    separately so we never emit a duplicate CREATE INDEX for their backing
    index)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            i.object_id AS table_object_id, i.name AS index_name, i.type,
            i.is_unique, ic.key_ordinal, ic.is_included_column,
            ic.is_descending_key, col.name AS column_name, i.filter_definition
        FROM sys.indexes i
        JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns col ON col.object_id = ic.object_id AND col.column_id = ic.column_id
        JOIN sys.tables t ON t.object_id = i.object_id
        WHERE t.is_ms_shipped = 0
            AND i.is_primary_key = 0 AND i.is_unique_constraint = 0
            AND i.type IN (1, 2) AND i.name IS NOT NULL
        ORDER BY i.object_id, i.name, ic.key_ordinal
        """
    )
    grouped = defaultdict(list)
    for row in cur.fetchall():
        grouped[(row.table_object_id, row.index_name)].append(row)

    for (obj_id, iname), rows in grouped.items():
        table = tables.get(obj_id)
        if table is None:
            continue
        key_cols = [
            (r.column_name, bool(r.is_descending_key))
            for r in sorted(rows, key=lambda r: r.key_ordinal)
            if not r.is_included_column
        ]
        include_cols = [r.column_name for r in rows if r.is_included_column]
        table.indexes.append({
            "name": iname,
            "is_unique": bool(rows[0].is_unique),
            "is_clustered": rows[0].type == 1,
            "key_columns": key_cols,
            "include_columns": include_cols,
            "filter": rows[0].filter_definition,
        })


def fetch_foreign_keys(conn, tables: dict) -> list:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            fk.object_id AS fk_object_id, fk.name AS fk_name,
            fk.parent_object_id, fk.referenced_object_id,
            fk.delete_referential_action_desc, fk.update_referential_action_desc,
            fkc.constraint_column_id, pc.name AS parent_column, rc.name AS referenced_column
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
        JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
        JOIN sys.tables pt ON pt.object_id = fk.parent_object_id
        JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
        WHERE pt.is_ms_shipped = 0 AND rt.is_ms_shipped = 0
        ORDER BY fk.object_id, fkc.constraint_column_id
        """
    )
    grouped = defaultdict(list)
    for row in cur.fetchall():
        grouped[row.fk_object_id].append(row)

    fks = []
    for fk_object_id, rows in grouped.items():
        first = rows[0]
        parent = tables.get(first.parent_object_id)
        referenced = tables.get(first.referenced_object_id)
        if parent is None or referenced is None:
            continue  # referenced/parent table not in our exported set -- skip, don't guess
        fk = {
            "name": first.fk_name,
            "parent": parent,
            "referenced": referenced,
            "columns": [(r.parent_column, r.referenced_column) for r in rows],
            "delete_action": first.delete_referential_action_desc,
            "update_action": first.update_referential_action_desc,
        }
        fks.append(fk)
        parent.outgoing_fks.append(fk)
    return fks


# --------------------------------------------------------------------------
# Dependency ordering (best-effort topological sort; cycles are broken and
# documented rather than causing a failure -- correctness does not depend
# on this order since FKs are added WITH NOCHECK after all data loads)
# --------------------------------------------------------------------------

def topological_order(tables: dict, fks: list) -> tuple[list, list]:
    deps = defaultdict(set)  # table depends on these tables
    for fk in fks:
        if fk["parent"].object_id != fk["referenced"].object_id:  # ignore self-refs
            deps[fk["parent"].object_id].add(fk["referenced"].object_id)

    all_ids = list(tables.keys())
    indegree = {oid: 0 for oid in all_ids}
    children = defaultdict(list)  # referenced -> [dependents]
    for oid, dep_set in deps.items():
        indegree[oid] = len(dep_set)
        for dep in dep_set:
            children[dep].append(oid)

    ready = deque(sorted(
        (oid for oid in all_ids if indegree[oid] == 0),
        key=lambda o: (tables[o].schema, tables[o].name),
    ))
    ordered = []
    indegree_work = dict(indegree)
    while ready:
        oid = ready.popleft()
        ordered.append(oid)
        for dependent in sorted(children[oid], key=lambda o: (tables[o].schema, tables[o].name)):
            indegree_work[dependent] -= 1
            if indegree_work[dependent] == 0:
                ready.append(dependent)

    remaining = [oid for oid in all_ids if oid not in ordered]
    if remaining:
        remaining.sort(key=lambda o: (tables[o].schema, tables[o].name))
        ordered.extend(remaining)

    cyclic_tables = [tables[oid].display_name for oid in remaining]
    return ordered, cyclic_tables


# --------------------------------------------------------------------------
# Column type rendering for CREATE TABLE
# --------------------------------------------------------------------------

_NO_LENGTH_TYPES = {
    "int", "bigint", "smallint", "tinyint", "bit", "money", "smallmoney",
    "date", "datetime", "smalldatetime", "uniqueidentifier", "xml", "text",
    "ntext", "image", "sql_variant", "hierarchyid", "geometry", "geography",
    "timestamp", "rowversion", "float", "real",
}
_CHAR_TYPES = {"char", "varchar", "nchar", "nvarchar", "binary", "varbinary"}
_UNICODE_TYPES = {"nchar", "nvarchar", "ntext"}
_DECIMAL_TYPES = {"decimal", "numeric"}
_SCALE_ONLY_TYPES = {"datetime2", "datetimeoffset", "time"}


def render_type(col: Column) -> str:
    t = col.type_name
    if t in _CHAR_TYPES:
        if col.max_length == -1:
            length = "MAX"
        elif t in ("nchar", "nvarchar"):
            length = str(col.max_length // 2)
        else:
            length = str(col.max_length)
        return f"[{t}]({length})"
    if t in _DECIMAL_TYPES:
        return f"[{t}]({col.precision},{col.scale})"
    if t in _SCALE_ONLY_TYPES:
        return f"[{t}]({col.scale})"
    if t in _NO_LENGTH_TYPES:
        return f"[{t}]"
    # Unknown/CLR/alias type -- emit as-is and flag for manual review.
    return f"[{t}] /* unrecognized type: verify on target server */"


def render_column_definition(col: Column) -> str:
    parts = [quoted(col.name)]
    if col.is_computed:
        persisted = " PERSISTED" if col.is_persisted else ""
        parts.append(f"AS {col.computed_definition}{persisted}")
        return " ".join(parts)
    parts.append(render_type(col))
    if col.is_identity:
        seed = col.seed_value if col.seed_value is not None else 1
        incr = col.increment_value if col.increment_value is not None else 1
        parts.append(f"IDENTITY({seed},{incr})")
    parts.append("NULL" if col.is_nullable else "NOT NULL")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Value -> SQL literal rendering (source data -> INSERT literal)
# --------------------------------------------------------------------------

def sql_literal(value, col: Column, warnings: list, table_name: str) -> str:
    if value is None:
        return "NULL"

    t = col.type_name

    if t == "bit":
        return "1" if value else "0"

    if t in ("int", "bigint", "smallint", "tinyint"):
        return str(int(value))

    if t in _DECIMAL_TYPES or t in ("money", "smallmoney"):
        if isinstance(value, decimal.Decimal):
            return format(value, "f")
        return format(decimal.Decimal(str(value)), "f")

    if t in ("float", "real"):
        return repr(float(value))

    if t == "uniqueidentifier":
        return f"'{value}'"

    if t in ("binary", "varbinary", "image"):
        data = bytes(value)
        if len(data) > LARGE_BINARY_WARN_BYTES:
            warnings.append(
                f"{table_name}: binary value of {len(data)} bytes emitted in full "
                f"(exceeds {LARGE_BINARY_WARN_BYTES} byte advisory threshold)"
            )
        return "0x" + data.hex() if data else "0x"

    if t == "date":
        return f"'{value.isoformat()}'"

    if t == "time":
        return f"'{value.strftime('%H:%M:%S.%f')}'"

    if t == "datetime2":
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S.%f')}'"

    if t in ("datetime", "smalldatetime"):
        # datetime/smalldatetime only accept up to 3 fractional digits when
        # converting FROM a string -- unlike datetime2, SQL Server does not
        # round a 6-digit microsecond string down, it raises Msg 241
        # "Conversion failed when converting date and/or time from character
        # string." Truncate to milliseconds ourselves instead.
        millis = value.microsecond // 1000
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}.{millis:03d}'"

    if t == "datetimeoffset":
        # Pre-formatted string via the ODBC output converter registered on
        # the connection (see _handle_datetimeoffset) -- passed straight
        # through untouched, just quoted.
        if isinstance(value, str):
            return f"'{value}'"
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S.%f %z')}'"

    if t in _UNICODE_TYPES or t == "xml":
        escaped = str(value).replace("'", "''")
        return f"N'{escaped}'"

    if t in ("char", "varchar", "text"):
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    if t == "sql_variant":
        if isinstance(value, bytes):
            return "0x" + value.hex()
        if isinstance(value, (int, float, decimal.Decimal)):
            return str(value)
        if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
            return f"'{value}'"
        escaped = str(value).replace("'", "''")
        return f"N'{escaped}'"

    # Unsupported/CLR type (geometry, geography, hierarchyid, ...): do not
    # guess at literal syntax -- emit NULL with a loud comment rather than
    # producing SQL that silently corrupts the value.
    warnings.append(
        f"{table_name}.{col.name}: unsupported type '{t}' for literal generation -- "
        f"value replaced with NULL, manual review required"
    )
    return "NULL /* unsupported type '%s' -- original value dropped */" % t


# --------------------------------------------------------------------------
# IsActive detection + type-aware comparator
# --------------------------------------------------------------------------

_STRING_TYPES = {"char", "varchar", "nchar", "nvarchar", "text", "ntext"}
_NUMERIC_TYPES = {
    "bit", "int", "bigint", "smallint", "tinyint", "decimal", "numeric",
    "money", "smallmoney", "float", "real",
}


def find_is_active_column(table: Table) -> Column | None:
    for col in table.columns:
        if col.name.lower() == "isactive" and not col.is_computed:
            return col
    return None


def is_active_predicate(col: Column) -> str:
    if col.type_name in _STRING_TYPES:
        return f"{quoted(col.name)} = '1'"
    # numeric/bit/anything else comparable to the integer literal 1
    return f"{quoted(col.name)} = 1"


def is_active_row_is_true(value, col: Column) -> bool:
    if value is None:
        return False
    if col.type_name in _STRING_TYPES:
        return str(value).strip() == "1"
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return bool(value)


# --------------------------------------------------------------------------
# Deterministic ORDER BY selection
# --------------------------------------------------------------------------

def choose_order_by(table: Table) -> tuple[list[str] | None, str]:
    if table.pk_columns:
        cols = [quoted(c) + (" DESC" if desc else "") for c, desc in table.pk_columns]
        return cols, f"primary key {table.pk_name}"

    for uq in table.unique_constraints:
        cols = [quoted(c) + (" DESC" if desc else "") for c, desc in uq["columns"]]
        return cols, f"unique constraint {uq['name']}"

    orderable = [c for c in table.columns if c.is_orderable]
    if orderable:
        return [quoted(c.name) for c in orderable], (
            "no PK/UNIQUE key -- fell back to ordering by all orderable columns"
        )

    return None, (
        "no PK/UNIQUE key and every column is a non-orderable LOB/CLR type "
        "-- deterministic ordering is not possible for this table"
    )


# --------------------------------------------------------------------------
# Data extraction
# --------------------------------------------------------------------------

def fetch_sample_rows(conn, table: Table, max_rows: int):
    is_active_col = find_is_active_column(table)
    table.is_active_column = is_active_col

    order_cols, reason = choose_order_by(table)
    table.order_by_columns = order_cols
    table.order_by_reason = reason

    insertable = table.insertable_columns
    if not insertable:
        return []  # e.g. table made entirely of computed/rowversion columns

    select_cols = ", ".join(quoted(c.name) for c in insertable)
    where_clause = f" WHERE {is_active_predicate(is_active_col)}" if is_active_col else ""
    order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""

    sql = (
        f"SELECT TOP ({max_rows}) {select_cols} FROM {table.qualified_name}"
        f"{where_clause}{order_clause}"
    )
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()

    if len(rows) > max_rows:  # defensive; TOP() already guarantees this
        raise AssertionError(f"{table.display_name}: fetched more than {max_rows} rows")

    if is_active_col is not None:
        idx = [c.name for c in insertable].index(is_active_col.name)
        for r in rows:
            if not is_active_row_is_true(r[idx], is_active_col):
                raise AssertionError(
                    f"{table.display_name}: IsActive filter leaked a non-active row"
                )

    return rows


def fetch_total_row_count(conn, table: Table) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table.qualified_name}")
    return cur.fetchone()[0]


# --------------------------------------------------------------------------
# Script generation
# --------------------------------------------------------------------------

class ScriptBuilder:
    def __init__(self, target_db: str, max_rows: int, source_database: str):
        self.target_db = target_db
        self.max_rows = max_rows
        self.source_database = source_database
        self.lines: list[str] = []
        self.stats = {
            "total_tables": 0,
            "tables_with_data": 0,
            "tables_without_data": 0,
            "total_rows": 0,
            "tables_filtered_by_is_active": 0,
            "tables_with_identity": 0,
            "tables_with_fk": 0,
            "cyclic_fk_tables": [],
            "no_deterministic_order_tables": [],
            "empty_reason": {},  # table display_name -> reason string
        }
        self.warnings: list[str] = []

    def add(self, text: str = ""):
        self.lines.append(text)

    def section(self, title: str):
        self.add("")
        self.add("-" * 60)
        self.add(f"-- {title}")
        self.add("-" * 60)
        self.add("")

    # -- 1. Database -------------------------------------------------
    def write_database_section(self):
        self.section("1. DATABASE")
        self.add(
            "-- Target database name is a sqlcmd scripting variable (survives GO\n"
            "-- batch separators, unlike a plain T-SQL DECLARE). To point this script\n"
            "-- at a different database, EDIT THE LINE BELOW directly -- sqlcmd\n"
            "-- scripting variables that are :setvar in the file always win over a\n"
            "-- command-line '-v TargetDatabaseName=...' override, so passing -v\n"
            "-- alongside this line has no effect; editing the literal below is the\n"
            "-- one supported way to change the target.\n"
            "-- Run this file with sqlcmd.exe, or in SSMS with Query > SQLCMD Mode enabled."
        )
        self.add(f':setvar TargetDatabaseName "{self.target_db}"')
        self.add("")
        self.add("IF DB_ID(N'$(TargetDatabaseName)') IS NULL")
        self.add("BEGIN")
        self.add("    CREATE DATABASE [$(TargetDatabaseName)];")
        self.add("END")
        self.add("GO")
        self.add("")
        self.add("USE [$(TargetDatabaseName)];")
        self.add("GO")

    # -- 2. Schemas ----------------------------------------------------
    def write_schema_section(self, schemas: list[str]):
        self.section("2. SCHEMAS")
        for schema in schemas:
            if schema.lower() == "dbo":
                continue
            self.add("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'%s')" % schema)
            self.add("BEGIN")
            self.add("    EXEC(N'CREATE SCHEMA %s');" % quoted(schema))
            self.add("END")
            self.add("GO")

    # -- 3. Tables -----------------------------------------------------
    def write_tables_section(self, tables: list[Table]):
        self.section("3. TABLES")
        for table in tables:
            self.add(f"-- {table.display_name}")
            self.add(f"CREATE TABLE {table.qualified_name}")
            self.add("(")
            col_lines = [
                "    " + render_column_definition(c)
                for c in sorted(table.columns, key=lambda c: c.column_id)
            ]
            self.add(",\n".join(col_lines))
            self.add(");")
            self.add("GO")
            self.add("")

    # -- 4. PK / Unique / Default / Check constraints ------------------
    def write_constraints_section(self, tables: list[Table]):
        self.section("4. PRIMARY KEYS / UNIQUE / DEFAULT / CHECK CONSTRAINTS")
        for table in tables:
            if table.pk_columns:
                cols = ", ".join(
                    f"{quoted(c)} {'DESC' if d else 'ASC'}" for c, d in table.pk_columns
                )
                self.add(
                    f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {quoted(table.pk_name)} "
                    f"PRIMARY KEY ({cols});"
                )
                self.add("GO")
            for uq in table.unique_constraints:
                cols = ", ".join(
                    f"{quoted(c)} {'DESC' if d else 'ASC'}" for c, d in uq["columns"]
                )
                self.add(
                    f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {quoted(uq['name'])} "
                    f"UNIQUE ({cols});"
                )
                self.add("GO")
            for dflt in table.default_constraints:
                self.add(
                    f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {quoted(dflt['name'])} "
                    f"DEFAULT {dflt['definition']} FOR {quoted(dflt['column'])};"
                )
                self.add("GO")
            for chk in table.check_constraints:
                self.add(
                    f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {quoted(chk['name'])} "
                    f"CHECK {chk['definition']};"
                )
                self.add("GO")

    # -- 5. Sample data --------------------------------------------------
    def write_data_for_table(self, table: Table, rows):
        insertable = table.insertable_columns
        self.add(f"-- {table.display_name}")

        if not insertable:
            self.add(f"-- No sample data available for {table.display_name} "
                      f"(every column is computed/rowversion -- nothing insertable)")
            self.stats["tables_without_data"] += 1
            self.stats["empty_reason"][table.display_name] = "no insertable columns"
            self.add("")
            return

        if not rows:
            if table.is_active_column is not None:
                total = table.total_row_count or 0
                reason = f"0 of {total} rows have {table.is_active_column.name} = 1"
            elif (table.total_row_count or 0) == 0:
                reason = "table is empty"
            else:
                reason = "no eligible rows found"
            self.add(f"-- No sample data available for {table.display_name} ({reason})")
            self.stats["tables_without_data"] += 1
            self.stats["empty_reason"][table.display_name] = reason
            self.add("")
            return

        self.stats["tables_with_data"] += 1
        self.stats["total_rows"] += len(rows)
        if table.is_active_column is not None:
            self.stats["tables_filtered_by_is_active"] += 1

        col_names = ", ".join(quoted(c.name) for c in insertable)
        use_identity_insert = table.has_identity and any(c.is_identity for c in insertable)

        if use_identity_insert:
            self.add(f"SET IDENTITY_INSERT {table.qualified_name} ON;")

        for row in rows:
            values = []
            for col, value in zip(insertable, row):
                values.append(sql_literal(value, col, self.warnings, table.display_name))
            self.add(
                f"INSERT INTO {table.qualified_name} ({col_names}) VALUES "
                f"({', '.join(values)});"
            )

        if use_identity_insert:
            self.add(f"SET IDENTITY_INSERT {table.qualified_name} OFF;")
        self.add("GO")
        self.add("")

    def write_data_section_header(self):
        self.section("5. SAMPLE DATA")
        self.add(f"-- Maximum {self.max_rows} rows per table, deterministic ORDER BY,")
        self.add("-- IsActive = 1 filter applied where that column exists.")
        self.add("")

    # -- 6. Foreign keys --------------------------------------------------
    def write_fk_section(self, fks: list):
        self.section("6. FOREIGN KEYS")
        self.add(
            "-- Added WITH NOCHECK: each table above was sampled independently\n"
            "-- (its own TOP-N / IsActive / ORDER BY), so a child row's FK value is\n"
            "-- not guaranteed to reference a row that survived the parent table's\n"
            "-- own sample. WITH NOCHECK loads the constraint definition without\n"
            "-- validating pre-existing sample rows against it, so the script cannot\n"
            "-- fail with an FK violation while still enforcing the constraint for\n"
            "-- anything inserted after this point."
        )
        self.add("")
        seen_tables = set()
        for fk in fks:
            parent, referenced = fk["parent"], fk["referenced"]
            self.stats["tables_with_fk"] += 1 if parent.display_name not in seen_tables else 0
            seen_tables.add(parent.display_name)
            pcols = ", ".join(quoted(c) for c, _ in fk["columns"])
            rcols = ", ".join(quoted(c) for _, c in fk["columns"])
            self.add(
                f"ALTER TABLE {parent.qualified_name} WITH NOCHECK ADD CONSTRAINT "
                f"{quoted(fk['name'])} FOREIGN KEY ({pcols}) "
                f"REFERENCES {referenced.qualified_name} ({rcols})"
            )
            extra = []
            if fk["delete_action"] and fk["delete_action"] != "NO_ACTION":
                extra.append(f"ON DELETE {fk['delete_action'].replace('_', ' ')}")
            if fk["update_action"] and fk["update_action"] != "NO_ACTION":
                extra.append(f"ON UPDATE {fk['update_action'].replace('_', ' ')}")
            if extra:
                self.add("    " + " ".join(extra))
            self.add(";")
            self.add("GO")

    # -- 7. Indexes --------------------------------------------------------
    def write_index_section(self, tables: list[Table]):
        self.section("7. INDEXES")
        for table in tables:
            for idx in table.indexes:
                unique = "UNIQUE " if idx["is_unique"] else ""
                clustered = "CLUSTERED" if idx["is_clustered"] else "NONCLUSTERED"
                key_cols = ", ".join(
                    f"{quoted(c)} {'DESC' if d else 'ASC'}" for c, d in idx["key_columns"]
                )
                stmt = (
                    f"CREATE {unique}{clustered} INDEX {quoted(idx['name'])} "
                    f"ON {table.qualified_name} ({key_cols})"
                )
                if idx["include_columns"]:
                    stmt += f" INCLUDE ({', '.join(quoted(c) for c in idx['include_columns'])})"
                if idx["filter"]:
                    stmt += f" WHERE {idx['filter']}"
                self.add(stmt + ";")
                self.add("GO")

    # -- 8. Validation summary --------------------------------------------
    def write_summary_section(self, tables: list[Table]):
        self.section("8. VALIDATION SUMMARY (generation-time)")
        s = self.stats
        lines = [
            f"Total tables found:              {s['total_tables']}",
            f"Tables exported:                 {s['total_tables']}",
            f"Tables with sample data:         {s['tables_with_data']}",
            f"Tables without sample data:      {s['tables_without_data']}",
            f"Total sample rows:               {s['total_rows']}",
            f"Tables filtered by IsActive:     {s['tables_filtered_by_is_active']}",
            f"Tables containing identity cols: {s['tables_with_identity']}",
            f"Tables containing foreign keys:  {s['tables_with_fk']}",
        ]
        if s["cyclic_fk_tables"]:
            lines.append(
                "Circular FK dependency detected among: " + ", ".join(s["cyclic_fk_tables"])
            )
            lines.append("  -> insert/creation order for these was broken arbitrarily (by name);")
            lines.append("     safe because FKs are added WITH NOCHECK after data load.")
        if s["no_deterministic_order_tables"]:
            lines.append("Tables with NO deterministic ordering available (documented, not an error):")
            for name, reason in s["no_deterministic_order_tables"]:
                lines.append(f"  - {name}: {reason}")
        if self.warnings:
            lines.append(f"Generator warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  - {w}")
        for line in lines:
            self.add("-- " + line)

        self.add("")
        self.add("-- Post-execution row count check (run automatically when this script executes):")
        self.add("PRINT '--- COSEC sample export: post-load row counts ---';")
        self.add("DECLARE @rowcnt bigint;")
        for table in tables:
            # PRINT cannot take a subquery directly (Msg 1046: "Subqueries are
            # not allowed in this context") -- assign to a variable first.
            # Also: sqlcmd strips a leading bracketed token from PRINT output
            # (e.g. a message starting '[dbo].[Foo]...' renders as '.[Foo]...'
            # -- verified against sqlcmd 16.0/ODBC Driver 17), so the message
            # is prefixed with a plain word to keep '[' from being the first
            # character.
            self.add(f"SET @rowcnt = (SELECT COUNT(*) FROM {table.qualified_name});")
            self.add(f"PRINT 'Table {table.display_name}: ' + CAST(@rowcnt AS varchar(20));")

    def render(self) -> str:
        header = [
            "/* =========================================================",
            "   COSEC DATABASE SAMPLE EXPORT",
            f"   Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"   Source Database: {self.source_database}",
            f"   Maximum sample rows per table: {self.max_rows}",
            "   IsActive filtering: enabled (type-aware, per-column detection)",
            "   Foreign keys: created WITH NOCHECK after data load (see section 6)",
            "   ========================================================= */",
        ]
        return "\n".join(header + self.lines) + "\n"


def generate(conn, target_db: str, max_rows: int, source_database: str) -> tuple[str, dict]:
    tables = fetch_tables(conn)
    fetch_columns(conn, tables)
    fetch_primary_and_unique_keys(conn, tables)
    fetch_check_constraints(conn, tables)
    fetch_default_constraints(conn, tables)
    fetch_indexes(conn, tables)
    fks = fetch_foreign_keys(conn, tables)

    ordered_ids, cyclic = topological_order(tables, fks)
    ordered_tables = [tables[oid] for oid in ordered_ids]

    builder = ScriptBuilder(target_db, max_rows, source_database)
    builder.stats["total_tables"] = len(tables)
    builder.stats["cyclic_fk_tables"] = cyclic
    builder.stats["tables_with_identity"] = sum(1 for t in tables.values() if t.has_identity)

    schemas = sorted({t.schema for t in tables.values()})

    builder.write_database_section()
    builder.write_schema_section(schemas)
    builder.write_tables_section(ordered_tables)
    builder.write_constraints_section(ordered_tables)

    builder.write_data_section_header()
    for table in ordered_tables:
        table.total_row_count = None
        rows = fetch_sample_rows(conn, table, max_rows)
        if not rows and table.insertable_columns:
            table.total_row_count = fetch_total_row_count(conn, table)
        if table.order_by_columns is None:
            builder.stats["no_deterministic_order_tables"].append(
                (table.display_name, table.order_by_reason)
            )
        builder.write_data_for_table(table, rows)

    builder.write_fk_section(fks)
    builder.write_index_section(ordered_tables)
    builder.write_summary_section(ordered_tables)

    return builder.render(), builder.stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help="Output .sql file path")
    parser.add_argument("--target-db", default="COSEC_SAMPLE", help="Target database name baked into the generated script")
    parser.add_argument("--max-rows", type=int, default=MAX_ROWS_DEFAULT)
    args = parser.parse_args()

    source_database = os.getenv("COSEC_DB_DATABASE", "COSEC")
    conn = connect_source()
    try:
        script, stats = generate(conn, args.target_db, args.max_rows, source_database)
    finally:
        conn.close()

    output_path = args.output or f"cosec_sample_export.sql"
    Path(output_path).write_text(script, encoding="utf-8")

    print(f"Wrote {output_path}")
    for k, v in stats.items():
        if isinstance(v, list):
            continue
        print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
