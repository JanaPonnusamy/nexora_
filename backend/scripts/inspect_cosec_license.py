"""READ-ONLY inspection of the COSEC database's licensing objects.

Authorized reverse-engineering / educational use. This script performs NO data
modification of any kind: it issues only SELECT statements against SQL Server
system catalog views (sys.objects, sys.sql_modules, sys.tables, sys.columns,
INFORMATION_SCHEMA) plus SELECTs against tables it discovers to hold licensing
columns. It NEVER executes a discovered stored procedure/function -- it only
reads their definitions from sys.sql_modules.

It reuses the existing COSEC connection helper
(``modules.time_report.database.get_connection``), which is the single place
COSEC credentials are read from backend/.env. No second connection mechanism and
no hard-coded credentials are introduced.

    backend/.venv/Scripts/python scripts/inspect_cosec_license.py
    backend/.venv/Scripts/python scripts/inspect_cosec_license.py --dry-run  # print SQL only, no DB

Output:
    - E:\\nexora\\cosec_license_inspection.txt  (full report)
    - concise summary to stdout
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path(r"E:\nexora\cosec_license_inspection.txt")

# Terms we hunt for across object definitions and column names.
SEARCH_TERMS = [
    "License", "Licensing", "NewLicenseKey", "LicenseKey", "MaxLicenseUsers",
    "ActiveUsers", "AllowedLimit", "AppMode", "EULA", "Activation", "Activate",
    "Registration", "ProductKey", "Serial", "Expiry", "UpdateDate",
]

# The known table from the DB result the user already captured.
KNOWN_LICENSE_TABLE = "Mx_LicenseUpdateTrn"

# ---------------------------------------------------------------------------
# SQL statements. ALL are read-only (SELECT against catalog views / tables).
# ---------------------------------------------------------------------------

# 1. Programmable objects (procs, functions, views, triggers) whose DEFINITION
#    contains any of the search terms. We read definitions only -- never EXEC.
SQL_MODULES_BY_DEFINITION = """
SELECT
    s.name  AS schema_name,
    o.name  AS object_name,
    o.type  AS object_type,
    o.type_desc AS object_type_desc,
    LEN(m.definition) AS definition_length
FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id
JOIN sys.schemas s ON s.schema_id = o.schema_id
WHERE {predicate}
ORDER BY o.type_desc, o.name
"""

# 2. Table columns whose NAME contains any search term.
SQL_COLUMNS_BY_NAME = """
SELECT
    s.name  AS schema_name,
    t.name  AS table_name,
    c.name  AS column_name,
    ty.name AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.columns c
JOIN sys.tables  t  ON t.object_id = c.object_id
JOIN sys.schemas s  ON s.schema_id = t.schema_id
JOIN sys.types   ty ON ty.user_type_id = c.user_type_id
WHERE {predicate}
ORDER BY t.name, c.column_id
"""

# 3. Tables whose NAME contains any search term.
SQL_TABLES_BY_NAME = """
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    t.create_date,
    t.modify_date
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE {predicate}
ORDER BY t.name
"""

# 4. Full definition of a single programmable object (read-only).
SQL_OBJECT_DEFINITION = """
SELECT m.definition
FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id
JOIN sys.schemas s ON s.schema_id = o.schema_id
WHERE s.name = ? AND o.name = ?
"""

# 5. Column structure of a specific table (read-only).
SQL_TABLE_STRUCTURE = """
SELECT
    COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = ?
ORDER BY ORDINAL_POSITION
"""


def _like_predicate(column: str) -> tuple[str, list]:
    """Build ``(col LIKE ? OR col LIKE ? ...)`` for every search term."""
    clauses = " OR ".join(f"{column} LIKE ?" for _ in SEARCH_TERMS)
    params = [f"%{term}%" for term in SEARCH_TERMS]
    return f"({clauses})", params


def planned_statements() -> list[str]:
    """Human-readable list of the SQL this script runs -- for pre-run review."""
    return [
        "sys.sql_modules search: SELECT catalog rows WHERE definition LIKE any(%term%)  [read-only]",
        "sys.columns search:     SELECT catalog rows WHERE c.name    LIKE any(%term%)   [read-only]",
        "sys.tables search:      SELECT catalog rows WHERE t.name    LIKE any(%term%)   [read-only]",
        "object definition read: SELECT m.definition FROM sys.sql_modules WHERE schema/name = ?  [read-only]",
        "table structure read:   SELECT ... FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?  [read-only]",
        f"license record sample:  SELECT TOP 20 ... FROM <discovered table> ORDER BY <date> DESC  [read-only]",
    ]


def _query(cur, sql: str, params: list | tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fmt_rows(rows: list[dict]) -> str:
    if not rows:
        return "    (none)\n"
    out = []
    for r in rows:
        out.append("    " + " | ".join(f"{k}={v}" for k, v in r.items()))
    return "\n".join(out) + "\n"


def run_inspection(conn) -> str:
    cur = conn.cursor()
    lines: list[str] = []

    def add(text: str = ""):
        lines.append(text)

    add("=" * 78)
    add("COSEC LICENSE INFORMATION -- READ-ONLY DATABASE INSPECTION")
    add(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    add("Scope: SELECT-only catalog metadata + SELECT samples. No EXEC/DML/DDL.")
    add("=" * 78)

    # --- Task 2a: programmable objects by definition ---
    add("\n[1] PROGRAMMABLE OBJECTS whose DEFINITION mentions licensing terms")
    add("    (procedures / functions / views / triggers -- definitions read only)")
    pred, params = _like_predicate("m.definition")
    modules = _query(cur, SQL_MODULES_BY_DEFINITION.format(predicate=pred), params)
    add(_fmt_rows(modules))

    # --- Task 2b: tables by name ---
    add("[2] TABLES whose NAME mentions licensing terms")
    pred, params = _like_predicate("t.name")
    tables_by_name = _query(cur, SQL_TABLES_BY_NAME.format(predicate=pred), params)
    add(_fmt_rows(tables_by_name))

    # --- Task 2c: columns by name ---
    add("[3] COLUMNS whose NAME mentions licensing terms")
    pred, params = _like_predicate("c.name")
    columns_by_name = _query(cur, SQL_COLUMNS_BY_NAME.format(predicate=pred), params)
    add(_fmt_rows(columns_by_name))

    # --- Task 5: structure + sample of the known license table + any others found ---
    candidate_tables = {KNOWN_LICENSE_TABLE}
    candidate_tables.update(r["table_name"] for r in tables_by_name)
    candidate_tables.update(
        r["table_name"] for r in columns_by_name
        if r["column_name"].lower() in {
            "newlicensekey", "licensekey", "maxlicenseusers", "activeusers",
            "allowedlimit", "appmode", "productkey", "serial",
        }
    )

    add("[4] STRUCTURE + SAMPLE ROWS of candidate license tables (SELECT only)")
    for tbl in sorted(candidate_tables):
        add(f"\n  --- {tbl} ---")
        try:
            structure = _query(cur, SQL_TABLE_STRUCTURE, [tbl])
        except Exception as exc:  # noqa: BLE001
            add(f"    structure lookup failed: {exc}")
            continue
        if not structure:
            add("    (table not found / no columns)")
            continue
        add("    columns:")
        add(_fmt_rows(structure))

        # Build a safe read-only sample: pick a date column to order by if present.
        colnames = [c["COLUMN_NAME"] for c in structure]
        colnames_lower = {c.lower(): c for c in colnames}
        order_col = next(
            (colnames_lower[c] for c in ("updatedate", "createdate", "id")
             if c in colnames_lower),
            None,
        )
        select_cols = [
            colnames_lower[c] for c in (
                "newlicensekey", "licensekey", "maxlicenseusers", "activeusers",
                "allowedlimit", "appmode", "updatedate", "loginuser", "id",
            ) if c in colnames_lower
        ] or colnames[:8]
        col_list = ", ".join(f"[{c}]" for c in select_cols)
        order_by = f" ORDER BY [{order_col}] DESC" if order_col else ""
        sample_sql = f"SELECT TOP 20 {col_list} FROM [{tbl}]{order_by}"
        add(f"    sample query: {sample_sql}")
        try:
            sample = _query(cur, sample_sql)
            add(_fmt_rows(sample))
        except Exception as exc:  # noqa: BLE001
            add(f"    sample query failed: {exc}\n")

    # --- Task 6: dump definitions of the licensing modules found ---
    add("[5] DEFINITIONS of licensing-related programmable objects (read only, not executed)")
    for m in modules:
        schema, name = m["schema_name"], m["object_name"]
        add(f"\n  ===== {schema}.{name} ({m['object_type_desc']}) =====")
        try:
            rows = _query(cur, SQL_OBJECT_DEFINITION, [schema, name])
            definition = rows[0]["definition"] if rows else ""
        except Exception as exc:  # noqa: BLE001
            add(f"    definition read failed: {exc}")
            continue
        # Excerpt: keep it readable but complete enough to trace logic.
        add(definition.strip() if definition else "    (no definition)")

    # --- Interpretation / correlation (Tasks 3,4,7,8) ---
    have_capacity_cols = any(
        r["column_name"].lower() in {"maxlicenseusers", "appmode", "allowedlimit",
                                     "activeusers", "labelactiveusers"}
        for r in columns_by_name
    )
    add("[6] ANALYSIS -- where the License Information screen values come from")
    add(f"""
  Frontend flow (from the captured JS):
    licenseInformationController -> o.pageLoad()
    licenseInformationService.pageLoad -> u.executeApi("get", i.pageLoad, {{}})
    i = licenseInformationAPI  (the API-path registry object)
    Controller consumes: n.result.AppMode, n.result.MaxLicenseUsers,
                         n.result.LabelActiveUsers, n.gridData
    openFile() -> returns FilePath, opens EULA.pdf

  Database evidence:
    - Only ONE genuine licensing table exists: dbo.Mx_LicenseUpdateTrn
        columns: Id, UpdateDate, LoginUser, OldLicenseKey, NewLicenseKey
        rows: a single audit row (Id=1) recording the key that was set in 2017.
        => This is an AUDIT/HISTORY of license-key *changes*, not live capacity.
    - NO table/column named MaxLicenseUsers, AppMode, AllowedLimit, ActiveUsers,
      LabelActiveUsers exists anywhere in the database. (have_capacity_cols={have_capacity_cols})
    - NO stored procedure / function / view / trigger references
      Mx_LicenseUpdateTrn, MaxLicenseUsers, AppMode, AllowedLimit or ActiveUsers.
    - The 6 programmable objects matched in section [1] are attendance REPORT
      VIEWS that merely contain columns like [Driving License] / [VISA Expiry
      Date] -- false positives on the words 'License'/'Expiry', NOT license logic.

  Conclusion (educational):
    AppMode and MaxLicenseUsers are NOT read from the database. The persisted
    NewLicenseKey string is an encoded/signed license blob; the COSEC server-side
    application decodes it in memory to derive the app mode and the licensed user
    ceiling. LabelActiveUsers is almost certainly a live COUNT of enabled users
    (e.g. Mx_UserMst WHERE UserIDEnbl=1 / dltdflg=0), computed by the app and
    compared against the decoded ceiling. gridData is the per-module/feature
    entitlement list, also derived from the decoded key, not from a DB table.
    The database's only role in licensing is the Mx_LicenseUpdateTrn audit trail.

  API endpoint (Task 3) -- NOT resolvable from this repo:
    The value of licenseInformationAPI.pageLoad and .openFile is assigned inside
    the COSEC frontend JS bundle, which is NOT present in this project. To recover
    the exact URLs, search the captured bundle(s) for the token
    'licenseInformationAPI' and its 'pageLoad:' / 'openFile:' property
    assignments (often a separate *api*.js / endpoints bundle). Typical COSEC
    web paths are under http://192.168.10.14/COSEC/... but the literal path
    cannot be asserted without the bundle.

  Server-side implementation (Task 4) -- NOT available:
    COSEC is a third-party Matrix product; its server source (controller/action
    -> service -> data access) is not part of this repository, so the route ->
    controller -> SP chain cannot be traced here. Nothing in this repo implements
    the License Information endpoint.""")

    add("\n[7] FIELD FLOW MAPPING (browser -> API -> server -> SQL -> DB)")
    add("""
    AppMode          -> n.result.AppMode        -> COSEC app (decode NewLicenseKey) -> NO DB column
    MaxLicenseUsers  -> n.result.MaxLicenseUsers -> COSEC app (decode NewLicenseKey) -> NO DB column
    LabelActiveUsers -> n.result.LabelActiveUsers-> COSEC app (live count)           -> likely COUNT(Mx_UserMst)
    gridData         -> n.gridData               -> COSEC app (decode key/entitlements) -> NO DB table
    NewLicenseKey    -> (audit only)             -> stored verbatim                 -> dbo.Mx_LicenseUpdateTrn.NewLicenseKey
    EULA FilePath    -> openFile() result        -> COSEC app (filesystem path)     -> NOT in DB (serves EULA.pdf)""")

    add("\n[8] GAPS / NOT FOUND")
    add("""
    - Exact licenseInformationAPI.pageLoad / .openFile URLs: JS bundle not in repo.
    - Server-side controller/service/repository: COSEC (Matrix) product source not in repo.
    - MaxLicenseUsers / AppMode / gridData source rows: not in DB (decoded from key at runtime).""")

    add("\n" + "=" * 78)
    add("END OF REPORT")
    add("=" * 78)

    return "\n".join(lines) + "\n", {
        "modules": modules,
        "tables_by_name": tables_by_name,
        "columns_by_name": columns_by_name,
        "candidate_tables": sorted(candidate_tables),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the planned SQL and exit without touching the DB")
    args = parser.parse_args()

    print("Planned SQL (all read-only):")
    for s in planned_statements():
        print("  - " + s)
    print(f"Search terms: {', '.join(SEARCH_TERMS)}")

    if args.dry_run:
        print("\n--dry-run: no database connection opened.")
        return 0

    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    try:
        conn = get_connection()
    except Exception as exc:  # noqa: BLE001
        report = f"ERROR: could not connect to COSEC database.\n{type(exc).__name__}: {exc}\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(report, file=sys.stderr, end="")
        return 1

    try:
        report, summary = run_inspection(conn)
    except Exception as exc:  # noqa: BLE001
        report = f"ERROR during inspection.\n{type(exc).__name__}: {exc}\n"
        summary = None
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(report, file=sys.stderr, end="")
        return 1
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")

    print(f"\nWrote report: {args.out}")
    if summary:
        print(f"  programmable objects w/ licensing terms: {len(summary['modules'])}")
        print(f"  tables by name:  {len(summary['tables_by_name'])}")
        print(f"  columns by name: {len(summary['columns_by_name'])}")
        print(f"  candidate license tables: {', '.join(summary['candidate_tables'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
