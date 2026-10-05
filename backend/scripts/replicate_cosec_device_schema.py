"""Replicate COSEC device/punch schema into your own DB (Cosec_Nexora).

READ-ONLY on COSEC (schema + master rows via SELECT). Creates matching tables in
the target DB (192.168.10.73 / Cosec_Nexora). The transaction/live table
Mx_ATDEventTrn is created EMPTY -- its rows come from the device push, not COSEC.
Master/reference tables are copied so punches can be interpreted.

Connections (no creds hard-coded):
  - COSEC source: modules.time_report.database.get_connection (COSEC_DB_* in .env)
  - Target      : DB_SERVER / DB_DATABASE / DB_USERNAME / DB_PASSWORD / DB_DRIVER

    backend/.venv/Scripts/python scripts/replicate_cosec_device_schema.py --check
    backend/.venv/Scripts/python scripts/replicate_cosec_device_schema.py
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Live transaction table -> created EMPTY (device push fills it).
STRUCTURE_ONLY = ["Mx_ATDEventTrn"]
# Master/reference tables -> structure + data copied (mandatory details).
COPY_MASTERS = ["Mx_EventMst", "Mx_UserMst"]
# View materialised into a real table (device inventory).
VIEW_TO_TABLE = [("Mx_VEW_DoorDetail", "Mx_DeviceList")]

# Data types whose (possibly large) contents we skip when copying (column is still
# created; value inserted as NULL). Keeps the copy light and avoids LOB issues.
LOB_SKIP = {"image", "text", "ntext", "xml", "varbinary", "geography", "geometry"}


def target_conn(database: str):
    import pyodbc
    s = os.getenv("DB_SERVER"); d = database
    u = os.getenv("DB_USERNAME"); p = os.getenv("DB_PASSWORD")
    drv = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    if not all((s, u, p)):
        raise RuntimeError("Target DB_* env not set (DB_SERVER/DB_USERNAME/DB_PASSWORD)")
    return pyodbc.connect(
        f"DRIVER={{{drv}}};SERVER={s};DATABASE={d};UID={u};PWD={p};TrustServerCertificate=yes;",
        autocommit=True,
    )


def sql_type(c) -> str:
    dt = c.DATA_TYPE.lower()
    if dt in ("varchar", "char", "nvarchar", "nchar", "varbinary", "binary"):
        n = c.CHARACTER_MAXIMUM_LENGTH
        length = "max" if n == -1 else (n if n else 1)
        return f"{dt}({length})"
    if dt in ("decimal", "numeric"):
        return f"{dt}({c.NUMERIC_PRECISION},{c.NUMERIC_SCALE or 0})"
    return dt


def get_columns(cur, table):
    cur.execute(
        """SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                  NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, ORDINAL_POSITION
           FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION""",
        (table,),
    )
    return cur.fetchall()


def get_pk(cur, table):
    cur.execute(
        """SELECT k.COLUMN_NAME
           FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS t
           JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
             ON k.CONSTRAINT_NAME=t.CONSTRAINT_NAME
           WHERE t.CONSTRAINT_TYPE='PRIMARY KEY' AND t.TABLE_NAME=?
           ORDER BY k.ORDINAL_POSITION""",
        (table,),
    )
    return [r.COLUMN_NAME for r in cur.fetchall()]


def build_create(table, cols, pk):
    defs = []
    for c in cols:
        nn = "NULL" if c.IS_NULLABLE == "YES" else "NOT NULL"
        defs.append(f"    [{c.COLUMN_NAME}] {sql_type(c)} {nn}")
    if pk and all(any(col.COLUMN_NAME == k for col in cols) for k in pk):
        defs.append("    CONSTRAINT [PK_%s] PRIMARY KEY (%s)"
                    % (table, ", ".join(f"[{k}]" for k in pk)))
    return (f"IF OBJECT_ID('dbo.[{table}]','U') IS NULL\nCREATE TABLE dbo.[{table}] (\n"
            + ",\n".join(defs) + "\n);")


def copy_table(src_cur, tgt_cur, src_name, tgt_name, cols):
    # columns we actually copy data for (skip heavy LOBs -> created but left NULL)
    copy_cols = [c.COLUMN_NAME for c in cols if c.DATA_TYPE.lower() not in LOB_SKIP]
    collist = ", ".join(f"[{c}]" for c in copy_cols)
    src_cur.execute(f"SELECT {collist} FROM [{src_name}]")
    rows = src_cur.fetchall()
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in copy_cols)
    tgt_cur.fast_executemany = True
    tgt_cur.executemany(
        f"INSERT INTO dbo.[{tgt_name}] ({collist}) VALUES ({placeholders})",
        [tuple(r) for r in rows],
    )
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="connect + show plan, create nothing")
    args = ap.parse_args()

    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    db_name = os.getenv("DB_DATABASE", "Cosec_Nexora")

    # ensure target database exists (connect to master)
    if not args.check:
        m = target_conn("master")
        mc = m.cursor()
        mc.execute(f"IF DB_ID(?) IS NULL EXEC('CREATE DATABASE [{db_name}]')", (db_name,))
        m.close()

    src = get_connection(); scur = src.cursor()

    plan = [(t, "structure-only (empty; device-fed)") for t in STRUCTURE_ONLY] \
        + [(t, "structure + master data") for t in COPY_MASTERS] \
        + [(v, f"view -> table {t} + data") for v, t in VIEW_TO_TABLE]
    print("Target:", os.getenv("DB_SERVER"), "/", db_name)
    print("Plan:")
    for t, how in plan:
        print(f"  {t:22} -> {how}")
    if args.check:
        # verify each source object exists + column count
        for t, _ in plan:
            cols = get_columns(scur, t)
            print(f"  [source] {t}: {len(cols)} columns")
        src.close()
        return 0

    tgt = target_conn(db_name); tcur = tgt.cursor()
    summary = []

    for table in STRUCTURE_ONLY:
        cols = get_columns(scur, table); pk = get_pk(scur, table)
        tcur.execute(build_create(table, cols, pk))
        summary.append(f"{table}: structure created ({len(cols)} cols), 0 rows (device-fed)")

    for table in COPY_MASTERS:
        cols = get_columns(scur, table); pk = get_pk(scur, table)
        tcur.execute(build_create(table, cols, pk))
        n = copy_table(scur, tcur, table, table, cols)
        summary.append(f"{table}: structure + {n} master rows copied")

    for view, table in VIEW_TO_TABLE:
        cols = get_columns(scur, view)  # views expose columns via INFORMATION_SCHEMA too
        tcur.execute(build_create(table, cols, []))
        n = copy_table(scur, tcur, view, table, cols)
        summary.append(f"{table}: materialised from {view} + {n} rows")

    src.close(); tgt.close()
    print("\nDONE:")
    for s in summary:
        print("  " + s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
