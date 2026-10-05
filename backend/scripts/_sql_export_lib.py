"""Shared SQL Server schema/data-export building blocks.

Extracted from cosec_db_extract.py (which stays untouched and self-contained)
so a second exporter (nexora_platform_db_extract.py) doesn't re-derive and
re-debug the same subtle logic -- notably the datetime/smalldatetime
fractional-second limit (SQL Server rejects a string with more than 3
fractional digits for those two types, Msg 241) and correct bracket/hex/
Unicode literal formatting for every SQL Server data type.

Every function here only ever issues metadata (sys.*) or SELECT queries --
callers are responsible for keeping it that way.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import struct
from collections import defaultdict, deque

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"

# SQL types that cannot appear in ORDER BY / comparisons.
NON_ORDERABLE_TYPES = {
    "text", "ntext", "image", "xml", "geography", "geometry",
    "hierarchyid", "sql_variant",
}

# Safety cap: a single binary literal larger than this is still emitted in
# full (never truncated/corrupted) but flagged with a preceding comment so
# the resulting file size growth is visible rather than silent.
LARGE_BINARY_WARN_BYTES = 2 * 1024 * 1024


def handle_datetimeoffset(raw):
    # ODBC SQL_SS_TIMESTAMPOFFSET_STRUCT: y,m,d,h,min,s,frac(uint32),tz_h,tz_m
    y, m, d, hh, mm, ss, frac, tz_h, tz_m = struct.unpack("<6hI2h", raw)
    sign = "+" if tz_h >= 0 else "-"
    return (
        f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}."
        f"{frac // 100:06d} {sign}{abs(tz_h):02d}:{abs(tz_m):02d}"
    )


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
        return self.type_name not in NON_ORDERABLE_TYPES and not self.is_computed


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
        # the connection (see handle_datetimeoffset) -- passed straight
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
