"""Matrix COSEC "Event/Data Push" receiver -> your own SQL Server.

Stands up a small HTTP endpoint that the Matrix devices POST punch events to in
real time. It:
  1. logs EVERY raw request (method, path, query, headers-sans-secrets, body) to
     E:\\nexora\\matrix_push_raw.log and to table dbo.matrix_push_raw, so the exact
     Matrix payload format is captured on the first packets;
  2. best-effort normalizes common punch fields and UPSERTs them into
     dbo.matrix_push_event (dedup by a content hash), and
  3. always answers 200 so the device marks the event delivered.

This talks ONLY to your own DB (PUNCH_DB_* env, same as the DB sync). It never
touches COSEC and issues no device commands. If PUNCH_DB_* is not set, it runs in
FILE-ONLY mode (still captures raw pushes) so you can start immediately.

RUN:
  set PUNCH_DB_SERVER/DATABASE/USERNAME/PASSWORD  (optional; file-only without them)
  backend/.venv/Scripts/python scripts/matrix_push_receiver.py --host 0.0.0.0 --port 8899

Then point each device's Data/Event Push URL at:
  http://192.168.10.80:8899/matrix/push
(Windows Firewall may need an inbound allow rule for the chosen port.)
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import uvicorn

RAW_LOG = Path(r"E:\nexora\matrix_push_raw.log")
SECRET_HEADERS = {"authorization", "cookie", "proxy-authorization"}

DDL = [
    """IF OBJECT_ID('dbo.matrix_push_raw','U') IS NULL
       CREATE TABLE dbo.matrix_push_raw(
         id BIGINT IDENTITY PRIMARY KEY, received_at DATETIME NOT NULL DEFAULT GETDATE(),
         remote_ip NVARCHAR(50), method NVARCHAR(10), path NVARCHAR(200),
         query NVARCHAR(MAX), content_type NVARCHAR(100), body NVARCHAR(MAX))""",
]
# Normalized punches land in dbo.Mx_ATDEventTrn (the COSEC-shaped table already
# created in Cosec_Nexora). IndexNo is generated locally (COSEC-independent) and
# duplicates are suppressed on (UserID, Edatetime, MID, DID).
INSERT_PUNCH = """
INSERT INTO dbo.Mx_ATDEventTrn (IndexNo, UserID, Edatetime, IOType, EventID, MID, DID, EvtSource, IDateTime, PROCFLG)
SELECT ISNULL((SELECT MAX(IndexNo) FROM dbo.Mx_ATDEventTrn),0)+1, ?, ?, ?, ?, ?, ?, 0, GETDATE(), 1
WHERE NOT EXISTS (
  SELECT 1 FROM dbo.Mx_ATDEventTrn
  WHERE UserID=? AND Edatetime=? AND ISNULL(MID,-1)=ISNULL(?,-1) AND ISNULL(DID,-1)=ISNULL(?,-1)
);
"""

# candidate field names Matrix pushes may use (mapped case-insensitively)
FIELD_ALIASES = {
    "user_id": ["userid", "user-id", "user", "uid", "empcode", "usrid"],
    "punch_dt": ["event-datetime", "eventdatetime", "datetime", "edatetime", "punchtime", "eventtime", "date-time"],
    "io_type": ["in-out", "inout", "iotype", "ioflg", "direction"],
    "event_id": ["event-id", "eventid", "evtid", "event"],
    "mid": ["mid", "deviceid", "device-id", "panelid"],
    "did": ["did", "doorid", "door-id"],
}


def _get(d: dict, aliases: list[str]):
    low = {k.lower(): v for k, v in d.items()}
    for a in aliases:
        if a in low and low[a] not in (None, ""):
            return low[a]
    return None


def _parse_dt(v):
    if not v:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S", "%Y%m%d%H%M%S", "%d-%m-%Y %H:%M"):
        try:
            return dt.datetime.strptime(str(v).strip(), fmt)
        except ValueError:
            continue
    return None


def _to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def target_conn_str():
    s, d = os.getenv("PUNCH_DB_SERVER"), os.getenv("PUNCH_DB_DATABASE")
    u, p = os.getenv("PUNCH_DB_USERNAME"), os.getenv("PUNCH_DB_PASSWORD")
    drv = os.getenv("PUNCH_DB_DRIVER", "ODBC Driver 17 for SQL Server")
    if not all((s, d, u, p)):
        return None
    return f"DRIVER={{{drv}}};SERVER={s};DATABASE={d};UID={u};PWD={p};TrustServerCertificate=yes;"


app = FastAPI(title="Matrix COSEC Push Receiver")
_conn = None


def _db():
    global _conn
    cs = target_conn_str()
    if not cs:
        return None
    if _conn is None:
        import pyodbc
        _conn = pyodbc.connect(cs, autocommit=True)
        cur = _conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
    return _conn


def _collect_fields(qs: dict, body: str, ctype: str) -> dict:
    fields = dict(qs)
    b = (body or "").strip()
    if not b:
        return fields
    if "json" in ctype or b[:1] in "{[":
        try:
            j = json.loads(b)
            if isinstance(j, dict):
                fields.update({str(k): v for k, v in j.items()})
        except Exception:
            pass
    elif "form" in ctype or "=" in b:
        for pair in b.replace("&", "\n").splitlines():
            if "=" in pair:
                k, _, v = pair.partition("=")
                fields[k.strip()] = v.strip()
    return fields


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT"])
async def receive(full_path: str, request: Request):
    raw = (await request.body()).decode("utf-8", "replace")
    qs = dict(request.query_params)
    ctype = request.headers.get("content-type", "")
    ip = request.client.host if request.client else ""
    ts = dt.datetime.now().isoformat(timespec="seconds")

    # 1) always log raw (headers minus secrets)
    hdrs = {k: v for k, v in request.headers.items() if k.lower() not in SECRET_HEADERS}
    RAW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RAW_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "ip": ip, "method": request.method,
                            "path": "/" + full_path, "query": qs, "ctype": ctype,
                            "headers": hdrs, "body": raw[:4000]}) + "\n")

    conn = _db()
    if conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.matrix_push_raw(remote_ip,method,path,query,content_type,body) "
            "VALUES (?,?,?,?,?,?)",
            (ip, request.method, "/" + full_path, json.dumps(qs), ctype, raw[:8000]),
        )

    # 2) best-effort normalize -> insert into the COSEC-shaped Mx_ATDEventTrn
    fields = _collect_fields(qs, raw, ctype)
    user_id = _get(fields, FIELD_ALIASES["user_id"])
    punch_dt = _parse_dt(_get(fields, FIELD_ALIASES["punch_dt"]))
    if conn and user_id and punch_dt:
        io_type = _to_int(_get(fields, FIELD_ALIASES["io_type"]))
        event_id = _to_int(_get(fields, FIELD_ALIASES["event_id"]))
        mid = _to_int(_get(fields, FIELD_ALIASES["mid"]))
        did = _to_int(_get(fields, FIELD_ALIASES["did"]))
        try:
            cur.execute(INSERT_PUNCH,
                        (str(user_id), punch_dt, io_type, event_id, mid, did,
                         str(user_id), punch_dt, mid, did))
        except Exception as e:  # noqa: BLE001 - raw is already saved; log & continue
            with RAW_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, "insert_error": str(e)}) + "\n")

    # 3) ack (some Matrix pushes look for a 200 / simple body)
    return PlainTextResponse("OK", status_code=200)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()
    mode = "SQL+file" if target_conn_str() else "FILE-ONLY (PUNCH_DB_* not set)"
    print(f"Matrix push receiver listening on {args.host}:{args.port}  mode={mode}")
    print(f"Point device push URL at: http://192.168.10.80:{args.port}/matrix/push")
    print(f"Raw log: {RAW_LOG}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
