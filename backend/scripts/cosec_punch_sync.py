"""Incremental sync of COSEC biometric punches into YOUR OWN SQL Server database.

READ-ONLY on COSEC (SELECT from dbo.Mx_ATDEventTrn only). All writes go to YOUR
target DB, never to COSEC. Idempotent: rows are MERGEd on index_no, and a watermark
(last synced IndexNo) is persisted in the target DB, so re-runs never duplicate or
skip. IndexNo in COSEC is append-only, which makes this safe and gap-free.

CONNECTIONS (no credentials hard-coded):
  - COSEC source : reuses modules.time_report.database.get_connection
                   (COSEC_DB_* in backend/.env)  -- read-only.
  - Target (yours): set these env vars (User scope or backend/.env):
        PUNCH_DB_SERVER, PUNCH_DB_DATABASE, PUNCH_DB_USERNAME, PUNCH_DB_PASSWORD
        PUNCH_DB_DRIVER   (optional, default "ODBC Driver 17 for SQL Server")

USAGE:
  # create schema + backfill everything, in batches
  backend/.venv/Scripts/python scripts/cosec_punch_sync.py
  # one batch only (e.g. for a scheduled task every few minutes)
  backend/.venv/Scripts/python scripts/cosec_punch_sync.py --once --batch 5000
  # dry run: show what WOULD sync, write nothing
  backend/.venv/Scripts/python scripts/cosec_punch_sync.py --dry-run
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

READ_SQL = """
SELECT TOP (?)
       e.IndexNo, e.UserID, e.Edatetime, e.IOType, e.EventID,
       m.EventDescr, e.MID, e.DID, e.EvtSource, e.PROCFLG
FROM Mx_ATDEventTrn e
LEFT JOIN Mx_EventMst m ON m.EVTID = e.EventID
WHERE e.IndexNo > ?
ORDER BY e.IndexNo
"""

DDL = [
    """IF OBJECT_ID('dbo.attendance_punch','U') IS NULL
       CREATE TABLE dbo.attendance_punch (
           index_no    BIGINT       NOT NULL PRIMARY KEY,
           user_id     NVARCHAR(15) NULL,
           punch_dt    DATETIME     NULL,
           io_type     INT          NULL,
           event_id    INT          NULL,
           event_desc  NVARCHAR(100) NULL,
           mid         INT          NULL,
           did         INT          NULL,
           evt_source  INT          NULL,
           proc_flg    INT          NULL,
           synced_at   DATETIME     NOT NULL DEFAULT GETDATE()
       )""",
    """IF OBJECT_ID('dbo.attendance_sync_state','U') IS NULL
       CREATE TABLE dbo.attendance_sync_state (
           source_name    NVARCHAR(50) NOT NULL PRIMARY KEY,
           last_index_no  BIGINT       NOT NULL,
           updated_at     DATETIME     NOT NULL DEFAULT GETDATE()
       )""",
    """IF NOT EXISTS (SELECT 1 FROM dbo.attendance_sync_state WHERE source_name='Mx_ATDEventTrn')
       INSERT INTO dbo.attendance_sync_state(source_name,last_index_no) VALUES ('Mx_ATDEventTrn',0)""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_attendance_punch_userdt')
       CREATE INDEX IX_attendance_punch_userdt ON dbo.attendance_punch(user_id, punch_dt)""",
]

MERGE_SQL = """
MERGE dbo.attendance_punch AS t
USING (SELECT ? AS index_no, ? AS user_id, ? AS punch_dt, ? AS io_type, ? AS event_id,
              ? AS event_desc, ? AS mid, ? AS did, ? AS evt_source, ? AS proc_flg) AS s
ON t.index_no = s.index_no
WHEN NOT MATCHED THEN
  INSERT (index_no,user_id,punch_dt,io_type,event_id,event_desc,mid,did,evt_source,proc_flg)
  VALUES (s.index_no,s.user_id,s.punch_dt,s.io_type,s.event_id,s.event_desc,s.mid,s.did,s.evt_source,s.proc_flg);
"""


def target_conn_str() -> str:
    server = os.getenv("PUNCH_DB_SERVER")
    database = os.getenv("PUNCH_DB_DATABASE")
    user = os.getenv("PUNCH_DB_USERNAME")
    pwd = os.getenv("PUNCH_DB_PASSWORD")
    driver = os.getenv("PUNCH_DB_DRIVER", "ODBC Driver 17 for SQL Server")
    missing = [n for n, v in (("PUNCH_DB_SERVER", server), ("PUNCH_DB_DATABASE", database),
                              ("PUNCH_DB_USERNAME", user), ("PUNCH_DB_PASSWORD", pwd)) if not v]
    if missing:
        raise RuntimeError("Target DB not configured: missing " + ", ".join(missing))
    return (f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"UID={user};PWD={pwd};TrustServerCertificate=yes;")


def to_int(v):
    return int(v) if v is not None else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--once", action="store_true", help="sync a single batch then stop")
    ap.add_argument("--dry-run", action="store_true", help="read from COSEC only; write nothing")
    args = ap.parse_args()

    sys.path.insert(0, str(BACKEND_DIR))
    from modules.time_report.database import get_connection  # COSEC (read-only)
    import pyodbc

    # ---- source (COSEC) ----
    src = get_connection()

    if args.dry_run:
        cur = src.cursor()
        cur.execute("SELECT MIN(IndexNo), MAX(IndexNo), COUNT(*) FROM Mx_ATDEventTrn")
        mn, mx, n = cur.fetchone()
        src.close()
        print(f"[dry-run] COSEC Mx_ATDEventTrn: IndexNo {mn}..{mx}, rows={n}")
        print("[dry-run] target env configured:", all(os.getenv(k) for k in
              ("PUNCH_DB_SERVER", "PUNCH_DB_DATABASE", "PUNCH_DB_USERNAME", "PUNCH_DB_PASSWORD")))
        return 0

    # ---- target (your DB) ----
    tgt = pyodbc.connect(target_conn_str())
    tcur = tgt.cursor()
    for stmt in DDL:
        tcur.execute(stmt)
    tgt.commit()

    tcur.execute("SELECT last_index_no FROM dbo.attendance_sync_state WHERE source_name='Mx_ATDEventTrn'")
    watermark = int(tcur.fetchone()[0])
    print(f"start watermark (last_index_no) = {watermark}")

    scur = src.cursor()
    total = 0
    while True:
        scur.execute(READ_SQL, (args.batch, watermark))
        rows = scur.fetchall()
        if not rows:
            break
        params = [
            (int(r.IndexNo), r.UserID, r.Edatetime, to_int(r.IOType), to_int(r.EventID),
             r.EventDescr, to_int(r.MID), to_int(r.DID), to_int(r.EvtSource), to_int(r.PROCFLG))
            for r in rows
        ]
        try:
            tcur.fast_executemany = True
        except Exception:
            pass
        tcur.executemany(MERGE_SQL, params)
        watermark = max(int(r.IndexNo) for r in rows)
        tcur.execute(
            "UPDATE dbo.attendance_sync_state SET last_index_no=?, updated_at=GETDATE() WHERE source_name='Mx_ATDEventTrn'",
            (watermark,),
        )
        tgt.commit()
        total += len(rows)
        print(f"  synced {len(rows)} (total {total}), watermark -> {watermark}")
        if args.once or len(rows) < args.batch:
            break

    src.close()
    tgt.close()
    print(f"done. rows synced this run = {total}. last_index_no = {watermark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
