"""READ-ONLY discovery of Matrix COSEC HARDWARE (panels/devices/doors) + their
network endpoints, to plan a DIRECT-FROM-DEVICE integration (not a DB sync).

No writes. SELECT against catalog views + device/panel master tables only.
Reuses modules.time_report.database.get_connection (creds from backend/.env).

    backend/.venv/Scripts/python scripts/inspect_cosec_devices.py
"""
from __future__ import annotations
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT = Path(r"E:\nexora\cosec_devices_report.txt")


def main() -> int:
    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    lines: list[str] = []
    add = lines.append
    conn = get_connection()
    cur = conn.cursor()

    def q(sql, p=()):
        cur.execute(sql, p)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    add("MATRIX COSEC HARDWARE INVENTORY -- READ-ONLY")
    add("=" * 70)

    # 1) locate candidate device/panel/door tables
    add("\n[1] candidate device / panel / door / controller tables")
    tbls = q("""SELECT s.name sch, t.name tbl, p.rows rows
                FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
                JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1)
                WHERE t.name LIKE '%Panel%' OR t.name LIKE '%Device%' OR t.name LIKE '%Door%'
                   OR t.name LIKE '%Controller%' OR t.name LIKE '%Reader%' OR t.name LIKE '%MID%'
                ORDER BY p.rows DESC""")
    for r in tbls:
        add(f"  {r['sch']}.{r['tbl']}  (~{r['rows']} rows)")

    # 2) any table with an IP-address-like column
    add("\n[2] tables exposing an IP/MAC/port column (device endpoints)")
    ipcols = q("""SELECT s.name sch, t.name tbl, c.name col
                  FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id
                  JOIN sys.schemas s ON s.schema_id=t.schema_id
                  WHERE c.name LIKE '%IP%' OR c.name LIKE '%MAC%' OR c.name LIKE '%Port%'
                     OR c.name LIKE '%Address%'
                  ORDER BY t.name, c.name""")
    for r in ipcols:
        add(f"  {r['sch']}.{r['tbl']}.{r['col']}")

    # 3) door-detail view (known to carry IP/MAC + device name)
    add("\n[3] Mx_VEW_DoorDetail sample (device/door -> IP/MAC)")
    try:
        rows = q("SELECT TOP 40 * FROM Mx_VEW_DoorDetail")
        if rows:
            add("    columns: " + ", ".join(rows[0].keys()))
            for r in rows:
                add("    " + " | ".join(f"{k}={v}" for k, v in r.items()))
        else:
            add("    (no rows)")
    except Exception as e:  # noqa: BLE001
        add(f"    (failed: {e})")

    # 4) which MIDs are actually producing punches (from the event stream)
    add("\n[4] active MIDs in the punch stream (device ids seen in Mx_ATDEventTrn)")
    try:
        rows = q("""SELECT e.MID, COUNT(*) AS punches, MAX(e.Edatetime) AS last_seen
                    FROM Mx_ATDEventTrn e
                    WHERE e.Edatetime > DATEADD(day,-30,GETDATE())
                    GROUP BY e.MID ORDER BY punches DESC""")
        for r in rows:
            add(f"    MID={r['MID']}  punches(30d)={r['punches']}  last_seen={r['last_seen']}")
    except Exception as e:  # noqa: BLE001
        add(f"    (failed: {e})")

    conn.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = "\n".join(lines) + "\n"
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"(report: {OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
