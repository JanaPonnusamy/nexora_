"""READ-ONLY: inspect COSEC's API config tables + sample the raw punch stream, to
plan an EXTERNAL sync. No writes. Reuses time_report.get_connection.

    backend/.venv/Scripts/python scripts/inspect_cosec_api_and_punches.py

API-key hygiene: if the API config holds a key/secret-looking column, its value is
MASKED in output (length only). Ask before revealing it in cleartext.
"""
from __future__ import annotations
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT = Path(r"E:\nexora\cosec_api_and_punches_report.txt")
SECRET_COL = ("key", "secret", "token", "pwd", "pass", "apikey")


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

    def mask(colname, val):
        if val is None:
            return None
        if any(s in colname.lower() for s in SECRET_COL):
            return f"<{len(str(val))} chars, masked>"
        return val

    add("COSEC API CONFIG + PUNCH STREAM -- READ-ONLY")
    add("=" * 70)

    for tbl in ("Mx_APITblMst", "MX_APITBLDET"):
        cols = q("""SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION""", (tbl,))
        if not cols:
            add(f"\n[{tbl}] not found")
            continue
        add(f"\n[{tbl}] columns:")
        for c in cols:
            add(f"    {c['COLUMN_NAME']} {c['DATA_TYPE']}"
                f"{('('+str(c['CHARACTER_MAXIMUM_LENGTH'])+')') if c['CHARACTER_MAXIMUM_LENGTH'] else ''}")
        try:
            rows = q(f"SELECT TOP 20 * FROM [{tbl}]")
            add(f"  rows ({len(rows)}), secret-like columns masked:")
            for r in rows:
                add("    " + " | ".join(f"{k}={mask(k, v)}" for k, v in r.items()))
        except Exception as e:  # noqa: BLE001
            add(f"  (row read failed: {e})")

    # Punch stream sample + watermark bounds
    add("\n[Mx_ATDEventTrn] latest 8 punches (read-only sample)")
    try:
        rows = q("""SELECT TOP 8 IndexNo, UserID, Edatetime, IOType, MID, DID, EventID, EvtSource, PROCFLG
                    FROM Mx_ATDEventTrn ORDER BY IndexNo DESC""")
        for r in rows:
            add("    " + " | ".join(f"{k}={v}" for k, v in r.items()))
    except Exception as e:  # noqa: BLE001
        add(f"    (failed: {e})")

    add("\n[Mx_ATDEventTrn] watermark bounds (for incremental sync)")
    try:
        b = q("""SELECT MIN(IndexNo) AS min_ix, MAX(IndexNo) AS max_ix,
                        MIN(Edatetime) AS min_dt, MAX(Edatetime) AS max_dt, COUNT(*) AS n
                 FROM Mx_ATDEventTrn""")[0]
        add(f"    IndexNo: {b['min_ix']} .. {b['max_ix']}   rows={b['n']}")
        add(f"    Edatetime: {b['min_dt']} .. {b['max_dt']}")
    except Exception as e:  # noqa: BLE001
        add(f"    (failed: {e})")

    # Event code meanings (Mx_EventMst) so external DB can decode EventID
    add("\n[Mx_EventMst] event-code lookup (first 15)")
    try:
        rows = q("SELECT TOP 15 EVTID, EventDescr FROM Mx_EventMst ORDER BY EVTID")
        for r in rows:
            add(f"    {r['EVTID']} = {r['EventDescr']}")
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
