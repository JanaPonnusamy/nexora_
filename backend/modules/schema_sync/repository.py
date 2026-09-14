"""Live SQL Server connections + metadata introspection for Schema Sync.

Unlike backend/config/database.py (which always connects to THIS tenant's
fixed HO database from env vars), every connection here is user-supplied at
request time: an arbitrary Dev (source, read-only) server and an arbitrary
Production/HO (target) server, each identified by host/port/database/
username/password from the UI form. Nothing here reads or writes env vars.
"""
from __future__ import annotations

import pyodbc

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


def _conn_str(conn: dict, database: str | None = None, autocommit_master: bool = False) -> str:
    driver = conn.get("driver") or _DEFAULT_DRIVER
    host = conn["host"]
    port = conn.get("port") or 1433
    db = database if database is not None else conn["database"]
    parts = [
        f"DRIVER={{{driver}}};",
        f"SERVER={host},{port};",
        f"DATABASE={db};",
        "TrustServerCertificate=yes;",
        f"UID={conn['username']};",
        f"PWD={conn['password']};",
    ]
    return "".join(parts)


def connect(conn: dict, database: str | None = None, timeout: int = 10, autocommit: bool = False):
    cs = _conn_str(conn, database=database)
    return pyodbc.connect(cs, timeout=timeout, autocommit=autocommit)


def database_exists(conn: dict) -> bool:
    with connect(conn, database="master") as c:
        cur = c.cursor()
        cur.execute("SELECT 1 FROM sys.databases WHERE name = ?", conn["database"])
        return cur.fetchone() is not None


def test_connection(conn: dict) -> dict:
    """Connects to 'master' on the server first (so a missing target database
    doesn't look like a bad host/credentials), then checks whether the named
    database exists."""
    try:
        with connect(conn, database="master") as c:
            cur = c.cursor()
            cur.execute("SELECT @@VERSION")
            version = cur.fetchone()[0]
            exists = database_exists(conn)
            return {
                "ok": True,
                "database_exists": exists,
                "message": "Connected" if exists else "Connected to server; database does not exist yet",
                "server_version": str(version).splitlines()[0] if version else None,
            }
    except pyodbc.Error as exc:
        return {"ok": False, "database_exists": False, "message": str(exc), "server_version": None}


def ensure_database(conn: dict) -> dict:
    if database_exists(conn):
        return {"ok": True, "created": False, "message": "Database already exists"}
    try:
        with connect(conn, database="master", autocommit=True) as c:
            cur = c.cursor()
            # Database names can't be parameterized; identifier is bracket-quoted
            # and any embedded ']' doubled to neutralise injection via the name.
            safe_name = conn["database"].replace("]", "]]")
            cur.execute(f"CREATE DATABASE [{safe_name}]")
        return {"ok": True, "created": True, "message": "Database created"}
    except pyodbc.Error as exc:
        return {"ok": False, "created": False, "message": str(exc)}


# ---------------------------------------------------------------------------
# Metadata introspection (live, via sys.* catalog views - no truncation, no
# text-dump parsing).
# ---------------------------------------------------------------------------

_COLUMNS_SQL = """
SELECT
    s.name AS SchemaName,
    t.name AS TableName,
    c.column_id AS ColumnOrder,
    c.name AS ColumnName,
    ty.name AS DataType,
    c.max_length AS MaxLength,
    c.precision AS Precision,
    c.scale AS Scale,
    c.is_nullable AS IsNullable,
    c.is_identity AS IsIdentity,
    dc.definition AS DefaultDefinition
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, c.column_id
"""

_PK_SQL = """
SELECT s.name AS SchemaName, t.name AS TableName, kc.name AS PkName,
       ic.key_ordinal AS ColumnOrder, c.name AS ColumnName
FROM sys.key_constraints kc
JOIN sys.tables t ON t.object_id = kc.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE kc.type = 'PK'
ORDER BY s.name, t.name, ic.key_ordinal
"""

_FK_SQL = """
SELECT s.name AS SchemaName, t.name AS TableName, fk.name AS FkName,
       fkc.constraint_column_id AS ColumnOrder, c.name AS ColumnName,
       rs.name AS RefSchema, rt.name AS RefTable, rc.name AS RefColumn
FROM sys.foreign_keys fk
JOIN sys.tables t ON t.object_id = fk.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns c ON c.object_id = fkc.parent_object_id AND c.column_id = fkc.parent_column_id
JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
ORDER BY s.name, t.name, fk.name, fkc.constraint_column_id
"""

_UQ_SQL = """
SELECT s.name AS SchemaName, t.name AS TableName, kc.name AS UqName,
       ic.key_ordinal AS ColumnOrder, c.name AS ColumnName
FROM sys.key_constraints kc
JOIN sys.tables t ON t.object_id = kc.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE kc.type = 'UQ'
ORDER BY s.name, t.name, ic.key_ordinal
"""

_INDEX_SQL = """
SELECT s.name AS SchemaName, t.name AS TableName, i.name AS IndexName,
       i.type_desc AS IndexType, i.is_unique AS IsUnique,
       i.is_primary_key AS IsPrimaryKey, i.is_unique_constraint AS IsUniqueConstraint,
       ic.key_ordinal AS KeyOrdinal, ic.index_column_id AS ColumnOrder,
       c.name AS ColumnName, ic.is_descending_key AS IsDescending,
       ic.is_included_column AS IsIncluded
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.name IS NOT NULL AND t.is_ms_shipped = 0
ORDER BY s.name, t.name, i.name, ic.is_included_column, ic.key_ordinal, ic.index_column_id
"""

_CHECK_SQL = """
SELECT s.name AS SchemaName, t.name AS TableName, cc.name AS CheckName, cc.definition AS Definition
FROM sys.check_constraints cc
JOIN sys.tables t ON t.object_id = cc.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
"""

_PROGRAMMABLE_SQL = """
SELECT s.name AS SchemaName, o.name AS ObjectName, o.type_desc AS TypeDesc,
       m.definition AS Definition, p.name AS ParentTableName
FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id
JOIN sys.schemas s ON s.schema_id = o.schema_id
LEFT JOIN sys.objects p ON p.object_id = o.parent_object_id
WHERE o.is_ms_shipped = 0
  AND o.type IN ('P','V','FN','TF','IF','TR')
"""


def _rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_snapshot(conn: dict) -> dict:
    """Full live metadata snapshot: tables/columns, PK, FK, unique, indexes,
    check constraints, and every programmable object with its FULL
    (untruncated) definition straight from sys.sql_modules."""
    with connect(conn) as c:
        cur = c.cursor()
        cur.execute(_COLUMNS_SQL)
        columns = _rows(cur)
        cur.execute(_PK_SQL)
        pks = _rows(cur)
        cur.execute(_FK_SQL)
        fks = _rows(cur)
        cur.execute(_UQ_SQL)
        uqs = _rows(cur)
        cur.execute(_INDEX_SQL)
        indexes = _rows(cur)
        cur.execute(_CHECK_SQL)
        checks = _rows(cur)
        cur.execute(_PROGRAMMABLE_SQL)
        programmables = _rows(cur)
    return {
        "columns": columns,
        "pks": pks,
        "fks": fks,
        "uqs": uqs,
        "indexes": indexes,
        "checks": checks,
        "programmables": programmables,
    }


def execute_ddl(conn: dict, sql: str) -> None:
    """Runs a single DDL/DML batch against the target. autocommit=True so each
    statement takes effect independently - a later failing statement in a
    one-click apply run must not roll back the ones that already succeeded."""
    with connect(conn, autocommit=True) as c:
        cur = c.cursor()
        cur.execute(sql)
