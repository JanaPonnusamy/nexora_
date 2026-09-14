"""NEXORA_PLATFORM database extraction utility.

Connects READ-ONLY to the live NEXORA_PLATFORM SQL Server (backend/.env
DB_SERVER/DB_DATABASE/DB_USERNAME/DB_PASSWORD, the same connection used by
the running backend -- see backend/config/database.py) and generates a
single, self-contained .sql script that recreates the ENTIRE database:
every schema, table, column/data type, PK/unique/default/check constraint,
foreign key, index, and stored procedure -- plus full data for every table
except the schemas listed in --skip-data-schemas (default: sync), whose
structure is still recreated but with zero rows.

Only SELECT and metadata (sys.*) queries are ever issued against the
source database -- no INSERT/UPDATE/DELETE/ALTER/DROP/TRUNCATE.

Usage:
    python backend/scripts/nexora_platform_db_extract.py [--output PATH]
        [--target-db NAME] [--skip-data-schemas sync,...]

Shares its metadata/type/literal-rendering logic with cosec_db_extract.py
via _sql_export_lib.py (see that module's docstring for why: several of
these SQL Server quirks -- datetime string-conversion precision, PRINT not
accepting a subquery argument, sqlcmd stripping a leading bracketed token
from PRINT output -- were only discovered by actually executing a generated
script end-to-end, and are worth getting right exactly once).

Design notes specific to this exporter (COSEC's script covers the FK
WITH-NOCHECK and target-database-name rationale, which apply unchanged
here):

* Full-table data is streamed directly to disk (fetchmany() in batches,
  multi-row INSERT statements written as they're built) rather than
  accumulated in memory -- several tables here have 500K-1.2M rows, and
  holding the whole rendered script as one big string/list (as the much
  smaller COSEC export does) would use gigabytes of RAM for no reason.
* Schemas are collected from BOTH tables AND stored procedures. NEXORA_
  PLATFORM has a `stock` schema that owns procedures but no tables --
  deriving the schema list from tables alone would create CREATE PROCEDURE
  statements targeting a schema that was never CREATE SCHEMA'd.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ for config.database

import _sql_export_lib as lib  # noqa: E402
from config.database import get_connection  # noqa: E402

FETCH_BATCH = 5000
ROWS_PER_INSERT = 250
PROGRESS_EVERY_ROWS = 100_000
DEFAULT_SKIP_DATA_SCHEMAS = {"sync"}


def connect_source():
    conn = get_connection()
    try:
        conn.add_output_converter(-155, lib.handle_datetimeoffset)  # SQL_SS_TIMESTAMPOFFSET
    except AttributeError:
        pass  # non-pyodbc fallback connection -- no datetimeoffset columns observed anyway
    return conn


# --------------------------------------------------------------------------
# Stored procedures
# --------------------------------------------------------------------------

def fetch_procedures(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.name AS schema_name, p.name AS proc_name, sm.definition
        FROM sys.procedures p
        JOIN sys.schemas s ON s.schema_id = p.schema_id
        JOIN sys.sql_modules sm ON sm.object_id = p.object_id
        WHERE p.is_ms_shipped = 0
        ORDER BY s.name, p.name
        """
    )
    procs = []
    for row in cur.fetchall():
        procs.append({
            "schema": row.schema_name,
            "name": row.proc_name,
            "definition": row.definition,
        })
    return procs


# --------------------------------------------------------------------------
# Writer -- streams directly to disk instead of accumulating in memory
# --------------------------------------------------------------------------

class Writer:
    def __init__(self, fh):
        self.fh = fh

    def write(self, text: str = ""):
        self.fh.write(text)
        self.fh.write("\n")

    def section(self, title: str):
        self.write("")
        self.write("-" * 60)
        self.write(f"-- {title}")
        self.write("-" * 60)
        self.write("")


def write_database_section(w: Writer, target_db: str):
    w.section("1. DATABASE")
    w.write(
        "-- Target database name is a sqlcmd scripting variable (survives GO\n"
        "-- batch separators, unlike a plain T-SQL DECLARE). To point this script\n"
        "-- at a different database, EDIT THE LINE BELOW directly -- an in-file\n"
        "-- :setvar always overrides a command-line '-v TargetDatabaseName=...'.\n"
        "-- Run this file with sqlcmd.exe, or in SSMS with Query > SQLCMD Mode enabled."
    )
    w.write(f':setvar TargetDatabaseName "{target_db}"')
    w.write("")
    w.write("IF DB_ID(N'$(TargetDatabaseName)') IS NULL")
    w.write("BEGIN")
    w.write("    CREATE DATABASE [$(TargetDatabaseName)];")
    w.write("END")
    w.write("GO")
    w.write("")
    w.write("USE [$(TargetDatabaseName)];")
    w.write("GO")
    w.write("")
    w.write("-- Required before CREATE TABLE for any table with a computed column /")
    w.write("-- filtered index / indexed view (Msg 1934 otherwise). Standard SSMS-")
    w.write("-- script boilerplate.")
    w.write("SET ANSI_NULLS ON;")
    w.write("GO")
    w.write("SET QUOTED_IDENTIFIER ON;")
    w.write("GO")


def write_schema_section(w: Writer, schemas: list[str]):
    w.section("2. SCHEMAS")
    for schema in schemas:
        if schema.lower() == "dbo":
            continue
        w.write("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'%s')" % schema)
        w.write("BEGIN")
        w.write("    EXEC(N'CREATE SCHEMA %s');" % lib.quoted(schema))
        w.write("END")
        w.write("GO")


def write_tables_section(w: Writer, tables: list[lib.Table]):
    w.section("3. TABLES")
    for table in tables:
        w.write(f"-- {table.display_name}")
        w.write(f"CREATE TABLE {table.qualified_name}")
        w.write("(")
        col_lines = [
            "    " + lib.render_column_definition(c)
            for c in sorted(table.columns, key=lambda c: c.column_id)
        ]
        w.write(",\n".join(col_lines))
        w.write(");")
        w.write("GO")
        w.write("")


def write_constraints_section(w: Writer, tables: list[lib.Table]):
    w.section("4. PRIMARY KEYS / UNIQUE / DEFAULT / CHECK CONSTRAINTS")
    for table in tables:
        if table.pk_columns:
            cols = ", ".join(
                f"{lib.quoted(c)} {'DESC' if d else 'ASC'}" for c, d in table.pk_columns
            )
            w.write(
                f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {lib.quoted(table.pk_name)} "
                f"PRIMARY KEY ({cols});"
            )
            w.write("GO")
        for uq in table.unique_constraints:
            cols = ", ".join(
                f"{lib.quoted(c)} {'DESC' if d else 'ASC'}" for c, d in uq["columns"]
            )
            w.write(
                f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {lib.quoted(uq['name'])} "
                f"UNIQUE ({cols});"
            )
            w.write("GO")
        for dflt in table.default_constraints:
            w.write(
                f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {lib.quoted(dflt['name'])} "
                f"DEFAULT {dflt['definition']} FOR {lib.quoted(dflt['column'])};"
            )
            w.write("GO")
        for chk in table.check_constraints:
            w.write(
                f"ALTER TABLE {table.qualified_name} ADD CONSTRAINT {lib.quoted(chk['name'])} "
                f"CHECK {chk['definition']};"
            )
            w.write("GO")


def write_fk_section(w: Writer, fks: list, stats: dict):
    w.section("6. FOREIGN KEYS")
    w.write(
        "-- Added WITH NOCHECK. sync.* tables are exported with zero rows (their\n"
        "-- data is skipped -- see section 5), so any FK touching sync.* cannot be\n"
        "-- validated against real data. WITH NOCHECK loads every constraint's\n"
        "-- definition without checking pre-existing rows, so the script cannot\n"
        "-- fail with an FK violation while still enforcing the constraint for\n"
        "-- anything inserted after this point."
    )
    w.write("")
    seen_tables = set()
    for fk in fks:
        parent, referenced = fk["parent"], fk["referenced"]
        if parent.display_name not in seen_tables:
            stats["tables_with_fk"] += 1
        seen_tables.add(parent.display_name)
        pcols = ", ".join(lib.quoted(c) for c, _ in fk["columns"])
        rcols = ", ".join(lib.quoted(c) for _, c in fk["columns"])
        w.write(
            f"ALTER TABLE {parent.qualified_name} WITH NOCHECK ADD CONSTRAINT "
            f"{lib.quoted(fk['name'])} FOREIGN KEY ({pcols}) "
            f"REFERENCES {referenced.qualified_name} ({rcols})"
        )
        extra = []
        if fk["delete_action"] and fk["delete_action"] != "NO_ACTION":
            extra.append(f"ON DELETE {fk['delete_action'].replace('_', ' ')}")
        if fk["update_action"] and fk["update_action"] != "NO_ACTION":
            extra.append(f"ON UPDATE {fk['update_action'].replace('_', ' ')}")
        if extra:
            w.write("    " + " ".join(extra))
        w.write(";")
        w.write("GO")


def write_index_section(w: Writer, tables: list[lib.Table]):
    w.section("7. INDEXES")
    for table in tables:
        for idx in table.indexes:
            unique = "UNIQUE " if idx["is_unique"] else ""
            clustered = "CLUSTERED" if idx["is_clustered"] else "NONCLUSTERED"
            key_cols = ", ".join(
                f"{lib.quoted(c)} {'DESC' if d else 'ASC'}" for c, d in idx["key_columns"]
            )
            stmt = (
                f"CREATE {unique}{clustered} INDEX {lib.quoted(idx['name'])} "
                f"ON {table.qualified_name} ({key_cols})"
            )
            if idx["include_columns"]:
                stmt += f" INCLUDE ({', '.join(lib.quoted(c) for c in idx['include_columns'])})"
            if idx["filter"]:
                stmt += f" WHERE {idx['filter']}"
            w.write(stmt + ";")
            w.write("GO")


def write_procedures_section(w: Writer, procs: list[dict]):
    w.section("8. STORED PROCEDURES")
    for proc in procs:
        w.write(f"-- {lib.qualified(proc['schema'], proc['name'])}")
        w.write(proc["definition"].rstrip().rstrip(";") + ";")
        w.write("GO")
        w.write("")


# --------------------------------------------------------------------------
# Data -- streamed, full table (no cap), except skip-data schemas
# --------------------------------------------------------------------------

def write_data_for_table(w: Writer, conn, table: lib.Table, skip_data_schemas: set,
                          warnings: list, stats: dict, row_cap: int | None = None):
    insertable = table.insertable_columns
    w.write(f"-- {table.display_name}")

    if table.schema.lower() in skip_data_schemas:
        w.write(f"-- Data skipped for {table.display_name} (schema "
                f"'{table.schema}' excluded per --skip-data-schemas)")
        stats["tables_data_skipped"] += 1
        w.write("")
        return

    if not insertable:
        w.write(f"-- No data exported for {table.display_name} "
                 f"(every column is computed/rowversion -- nothing insertable)")
        stats["tables_without_data"] += 1
        w.write("")
        return

    select_cols = ", ".join(lib.quoted(c.name) for c in insertable)
    top_clause = f"TOP ({row_cap}) " if row_cap else ""
    sql = f"SELECT {top_clause}{select_cols} FROM {table.qualified_name}"
    cur = conn.cursor()
    cur.execute(sql)

    col_names = ", ".join(lib.quoted(c.name) for c in insertable)
    use_identity_insert = table.has_identity and any(c.is_identity for c in insertable)

    total_rows = 0
    wrote_any = False
    next_progress = PROGRESS_EVERY_ROWS
    while True:
        batch = cur.fetchmany(FETCH_BATCH)
        if not batch:
            break
        if not wrote_any:
            if use_identity_insert:
                w.write(f"SET IDENTITY_INSERT {table.qualified_name} ON;")
            wrote_any = True

        for i in range(0, len(batch), ROWS_PER_INSERT):
            chunk = batch[i:i + ROWS_PER_INSERT]
            value_tuples = []
            for row in chunk:
                values = [
                    lib.sql_literal(value, col, warnings, table.display_name)
                    for col, value in zip(insertable, row)
                ]
                value_tuples.append("(" + ", ".join(values) + ")")
            w.write(
                f"INSERT INTO {table.qualified_name} ({col_names}) VALUES\n"
                + ",\n".join(value_tuples) + ";"
            )
        total_rows += len(batch)
        w.write("GO")

        if total_rows >= next_progress:
            print(f"  ... {table.display_name}: {total_rows:,} rows written", flush=True)
            next_progress += PROGRESS_EVERY_ROWS

    if not wrote_any:
        w.write(f"-- No data exported for {table.display_name} (table is empty)")
        stats["tables_without_data"] += 1
        w.write("")
        return

    if use_identity_insert:
        w.write(f"SET IDENTITY_INSERT {table.qualified_name} OFF;")
        w.write("GO")
    w.write("")

    stats["tables_with_data"] += 1
    stats["total_rows"] += total_rows
    if total_rows >= PROGRESS_EVERY_ROWS:
        print(f"  done {table.display_name}: {total_rows:,} rows", flush=True)


def write_summary_section(w: Writer, tables: list[lib.Table], stats: dict,
                           skip_data_schemas: set, warnings: list, proc_count: int):
    w.section("9. VALIDATION SUMMARY (generation-time)")
    lines = [
        f"Total tables found:              {stats['total_tables']}",
        f"Tables with full data exported:  {stats['tables_with_data']}",
        f"Tables with no data (empty):     {stats['tables_without_data']}",
        f"Tables with data skipped:        {stats['tables_data_skipped']} "
        f"(schemas: {', '.join(sorted(skip_data_schemas))})",
        f"Total data rows exported:        {stats['total_rows']:,}",
        f"Tables containing identity cols: {stats['tables_with_identity']}",
        f"Tables containing foreign keys:  {stats['tables_with_fk']}",
        f"Stored procedures exported:      {proc_count}",
    ]
    if stats["cyclic_fk_tables"]:
        lines.append(
            "Circular FK dependency detected among: " + ", ".join(stats["cyclic_fk_tables"])
        )
        lines.append("  -> table creation order for these was broken arbitrarily (by name);")
        lines.append("     safe because FKs are added WITH NOCHECK after data load.")
    if warnings:
        lines.append(f"Generator warnings ({len(warnings)}):")
        for warn in warnings:
            lines.append(f"  - {warn}")
    for line in lines:
        w.write("-- " + line)

    w.write("")
    w.write("-- Post-execution row count check (run automatically when this script executes):")
    w.write("PRINT '--- NEXORA_PLATFORM export: post-load row counts ---';")
    w.write("DECLARE @rowcnt bigint;")
    for table in tables:
        w.write(f"SET @rowcnt = (SELECT COUNT(*) FROM {table.qualified_name});")
        w.write(f"PRINT 'Table {table.display_name}: ' + CAST(@rowcnt AS varchar(20));")


def write_header(w: Writer, source_database: str, skip_data_schemas: set):
    w.write("/* =========================================================")
    w.write("   NEXORA_PLATFORM DATABASE FULL EXPORT")
    w.write(f"   Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w.write(f"   Source Database: {source_database}")
    w.write(f"   Data skipped for schemas: {', '.join(sorted(skip_data_schemas))} "
             "(structure only, zero rows)")
    w.write("   All other schemas: full data, every row")
    w.write("   Foreign keys: created WITH NOCHECK after data load (see section 6)")
    w.write("   ========================================================= */")


def generate(conn, out_fh, target_db: str, skip_data_schemas: set, source_database: str,
             row_cap: int | None = None) -> dict:
    tables = lib.fetch_tables(conn)
    lib.fetch_columns(conn, tables)
    lib.fetch_primary_and_unique_keys(conn, tables)
    lib.fetch_check_constraints(conn, tables)
    lib.fetch_default_constraints(conn, tables)
    lib.fetch_indexes(conn, tables)
    fks = lib.fetch_foreign_keys(conn, tables)
    procs = fetch_procedures(conn)

    ordered_ids, cyclic = lib.topological_order(tables, fks)
    ordered_tables = [tables[oid] for oid in ordered_ids]

    stats = {
        "total_tables": len(tables),
        "tables_with_data": 0,
        "tables_without_data": 0,
        "tables_data_skipped": 0,
        "total_rows": 0,
        "tables_with_identity": sum(1 for t in tables.values() if t.has_identity),
        "tables_with_fk": 0,
        "cyclic_fk_tables": cyclic,
    }
    warnings: list = []

    table_schemas = {t.schema for t in tables.values()}
    proc_schemas = {p["schema"] for p in procs}
    schemas = sorted(table_schemas | proc_schemas)

    w = Writer(out_fh)
    write_header(w, source_database, skip_data_schemas)
    write_database_section(w, target_db)
    write_schema_section(w, schemas)
    write_tables_section(w, ordered_tables)
    write_constraints_section(w, ordered_tables)

    w.section("5. DATA")
    w.write(f"-- Full data for every table except: "
             f"{', '.join(sorted(skip_data_schemas))} (structure only, zero rows).")
    w.write("")
    for i, table in enumerate(ordered_tables, 1):
        print(f"[{i}/{len(ordered_tables)}] {table.display_name}", flush=True)
        write_data_for_table(w, conn, table, skip_data_schemas, warnings, stats, row_cap)

    write_fk_section(w, fks, stats)
    write_index_section(w, ordered_tables)
    write_procedures_section(w, procs)
    write_summary_section(w, ordered_tables, stats, skip_data_schemas, warnings, len(procs))

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="nexora_platform_export.sql")
    parser.add_argument("--target-db", default="NEXORA_PLATFORM_SAMPLE")
    parser.add_argument("--skip-data-schemas", default="sync",
                         help="Comma-separated schema names to recreate structurally but export with zero rows")
    parser.add_argument("--row-cap", type=int, default=None,
                         help="Diagnostic only: cap every table's data at N rows (TOP N) for a fast "
                              "full-coverage test run. Omit for a real export (full data, no cap).")
    args = parser.parse_args()

    skip_data_schemas = {s.strip().lower() for s in args.skip_data_schemas.split(",") if s.strip()}
    source_database = os.getenv("DB_DATABASE", "NEXORA_PLATFORM")

    conn = connect_source()
    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            stats = generate(conn, fh, args.target_db, skip_data_schemas, source_database, args.row_cap)
    finally:
        conn.close()

    print(f"\nWrote {args.output}")
    for k, v in stats.items():
        if isinstance(v, list):
            continue
        print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
