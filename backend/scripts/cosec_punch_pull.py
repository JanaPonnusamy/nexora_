"""READ-ONLY incremental extractor for COSEC biometric punches.

Pulls new rows from dbo.Mx_ATDEventTrn since a given IndexNo watermark, decodes
the event code, and writes them to CSV + JSON in E:\\nexora so you can verify the
end-to-end pull before landing the data in your own database. SELECT only -- COSEC
is never modified. Reuses modules.time_report.database.get_connection.

    # first peek: newest 500 punches
    backend/.venv/Scripts/python scripts/cosec_punch_pull.py --since 0 --limit 500

    # incremental: everything after the watermark you last stored
    backend/.venv/Scripts/python scripts/cosec_punch_pull.py --since 6232000

Prints the new max IndexNo -- persist that as your next --since / last_index_no.
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = Path(r"E:\nexora")

SQL = """
SELECT TOP (?)
       e.IndexNo, e.UserID, e.Edatetime, e.IOType, e.EventID,
       m.EventDescr, e.MID, e.DID, e.EvtSource, e.PROCFLG
FROM Mx_ATDEventTrn e
LEFT JOIN Mx_EventMst m ON m.EVTID = e.EventID
WHERE e.IndexNo > ?
ORDER BY e.IndexNo
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", type=int, default=0, help="pull rows with IndexNo greater than this")
    ap.add_argument("--limit", type=int, default=1000, help="max rows this batch")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(SQL, (args.limit, args.since))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "cosec_punches.csv"
    json_path = args.out / "cosec_punches.json"

    def norm(v):
        return v.isoformat(sep=" ") if hasattr(v, "isoformat") else v

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: norm(v) for k, v in r.items()})
    json_path.write_text(
        json.dumps([{k: norm(v) for k, v in r.items()} for r in rows], indent=2, default=str),
        encoding="utf-8",
    )

    new_watermark = max((r["IndexNo"] for r in rows), default=args.since)
    print(f"pulled {len(rows)} punches (IndexNo > {args.since})")
    if rows:
        first, last = rows[0], rows[-1]
        print(f"  first: IndexNo={first['IndexNo']} {first['UserID']} @ {norm(first['Edatetime'])} ({first['EventDescr']})")
        print(f"  last : IndexNo={last['IndexNo']} {last['UserID']} @ {norm(last['Edatetime'])} ({last['EventDescr']})")
    print(f"  new watermark (last_index_no) = {new_watermark}")
    print(f"  wrote {csv_path}")
    print(f"  wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
