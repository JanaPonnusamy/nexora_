"""READ-ONLY discovery of COSEC biometric/attendance event tables + any API/
integration config, to plan syncing device punch data into an EXTERNAL database.

No writes of any kind. SELECT against catalog views + a few sample SELECTs only.
Reuses modules.time_report.database.get_connection (creds from backend/.env).

    backend/.venv/Scripts/python scripts/inspect_cosec_device_data.py
"""
from __future__ import annotations
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT = Path(r"E:\nexora\cosec_device_data_report.txt")


def main() -> int:
    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    lines: list[str] = []
    add = lines.append

    conn = get_connection()
    cur = conn.cursor()

    def q(sql, params=()):
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    add("COSEC DEVICE / ATTENDANCE DATA -- READ-ONLY DISCOVERY")
    add("=" * 70)

    add("\n[1] Candidate event / punch / attendance tables")
    tbls = q(
        """SELECT s.name sch, t.name tbl, p.rows AS row_count
           FROM sys.tables t
           JOIN sys.schemas s ON s.schema_id = t.schema_id
           JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
           WHERE t.name LIKE '%Event%' OR t.name LIKE '%ATD%' OR t.name LIKE '%Punch%'
              OR t.name LIKE '%Attendance%' OR t.name LIKE '%DATD%'
           ORDER BY p.rows DESC"""
    )
    for r in tbls:
        add(f"  {r['sch']}.{r['tbl']}  (~{r['row_count']} rows)")

    add("\n[2] API / integration / data-push / key config tables")
    api = q(
        """SELECT s.name sch, t.name tbl
           FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
           WHERE t.name LIKE '%API%' OR t.name LIKE '%Integrat%' OR t.name LIKE '%DataPush%'
              OR t.name LIKE '%Push%' OR t.name LIKE '%ApiKey%' OR t.name LIKE '%Token%'
           ORDER BY t.name"""
    )
    for r in api:
        add(f"  {r['sch']}.{r['tbl']}")
    if not api:
        add("  (none found by name)")

    # Structure of the main raw attendance-event table if present
    for cand in ("Mx_ATDEventTrn", "Mx_ACSEventTrn"):
        cols = q(
            """SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, ORDINAL_POSITION
               FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION""",
            (cand,),
        )
        if not cols:
            continue
        add(f"\n[3] Structure of {cand} (raw device events)")
        for c in cols:
            add(f"    {c['ORDINAL_POSITION']:>2}. {c['COLUMN_NAME']} "
                f"{c['DATA_TYPE']}"
                f"{('('+str(c['CHARACTER_MAXIMUM_LENGTH'])+')') if c['CHARACTER_MAXIMUM_LENGTH'] else ''} "
                f"{'NULL' if c['IS_NULLABLE']=='YES' else 'NOT NULL'}")

    conn.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = "\n".join(lines) + "\n"
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"(report: {OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
