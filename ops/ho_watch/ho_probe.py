"""Read-only HO + database probe for the HO watcher.

Prints ONE JSON document of facts and exits 0 even when things are broken, so the
wrapper can hand the facts to a report step. It only reads: HTTP GET /health on
each HO, SELECTs against this node's database, and the tail of the backend log.
It never writes, kills sessions or restarts anything.

Run from the repo root with the backend venv:
    backend\\.venv\\Scripts\\python.exe ops\\ho_watch\\ho_probe.py
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

TARGETS_FILE = Path(__file__).with_name("targets.json")
DEFAULT_TARGETS = [
    {"name": "HO .80 (dev/federation home)", "url": "http://192.168.10.80:8000"},
    {"name": "HO .32 (SMS)", "url": "http://192.168.10.32:8000"},
    {"name": "HO .73 (main)", "url": "http://192.168.10.73:8000"},
]


def probe_http(target, timeout=8):
    started = time.time()
    out = {"name": target["name"], "url": target["url"]}
    for path in ("/health",):
        try:
            with urllib.request.urlopen(target["url"] + path, timeout=timeout) as resp:
                out.update(ok=resp.status == 200, status=resp.status, body=resp.read(200).decode("utf-8", "replace"))
        except Exception as exc:  # unreachable, timeout, 5xx
            code = getattr(exc, "code", None)
            out.update(ok=False, status=code, error=f"{type(exc).__name__}: {exc}"[:200])
    out["ms"] = int((time.time() - started) * 1000)
    return out


def query(cur, sql):
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, [str(v) if v is not None else None for v in row])) for row in cur.fetchall()]


def probe_db():
    facts = {}
    try:
        from config.database import get_connection

        conn = get_connection()
    except Exception as exc:
        return {"ok": False, "error": f"cannot connect: {type(exc).__name__}: {exc}"[:300]}
    try:
        cur = conn.cursor()
        facts["ok"] = True
        facts["databases"] = query(cur, "SELECT name, state_desc, user_access_desc FROM sys.databases WHERE database_id > 4")
        facts["bad_databases"] = [d["name"] for d in facts["databases"] if d["state_desc"] != "ONLINE" or d["user_access_desc"] != "MULTI_USER"]
        facts["blocked_requests"] = query(
            cur,
            "SELECT TOP 10 session_id, blocking_session_id, wait_type, DATEDIFF(SECOND, start_time, GETDATE()) AS running_s "
            "FROM sys.dm_exec_requests WHERE blocking_session_id <> 0 ORDER BY start_time",
        )
        facts["longest_requests"] = query(
            cur,
            "SELECT TOP 5 session_id, status, command, DATEDIFF(SECOND, start_time, GETDATE()) AS running_s "
            "FROM sys.dm_exec_requests WHERE session_id > 50 AND session_id <> @@SPID ORDER BY start_time",
        )
        facts["sessions"] = query(cur, "SELECT COUNT(*) AS n FROM sys.dm_exec_sessions WHERE is_user_process = 1")[0]["n"]
        try:
            from modules.sync import health_monitor

            status = health_monitor.current_status()
            facts["sync_issues"] = status.get("issues", [])
            facts["sync_all_good"] = status.get("all_good")
        except Exception as exc:
            facts["sync_issues_error"] = f"{type(exc).__name__}: {exc}"[:200]
    except Exception as exc:
        facts.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        conn.close()
    return facts


def backend_log_errors(limit=12):
    log = BACKEND / "logs" / "prod-8000.err.log"
    if not log.exists():
        log = BACKEND / "logs" / "backend.log"
    if not log.exists():
        return {"file": None}
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-4000:]
    hits = [ln.strip()[:240] for ln in lines if re.search(r"\b(ERROR|CRITICAL|Traceback|Exception)\b", ln)]
    return {"file": log.name, "last_written": datetime.fromtimestamp(log.stat().st_mtime).isoformat(timespec="seconds"), "note": "an error log is only written when an error happens; an old date does NOT mean the backend was idle", "recent_errors": hits[-limit:]}


def main():
    targets = DEFAULT_TARGETS
    if TARGETS_FILE.exists():
        targets = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    facts = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "host": os.environ.get("COMPUTERNAME", ""),
        "hos": [probe_http(t) for t in targets],
        "database": probe_db(),
        "backend_log": backend_log_errors(),
    }
    # One-line verdict computed without AI, so alerts still work if Claude is unavailable.
    problems = [f"{h['name']} unreachable ({h.get('error') or h.get('status')})" for h in facts["hos"] if not h["ok"]]
    db = facts["database"]
    if not db.get("ok"):
        problems.append(f"database: {db.get('error')}")
    else:
        if db.get("bad_databases"):
            problems.append("databases not ONLINE/MULTI_USER: " + ", ".join(db["bad_databases"]))
        if db.get("blocked_requests"):
            problems.append(f"{len(db['blocked_requests'])} blocked SQL request(s)")
        if db.get("sync_issues"):
            problems.append(f"{len(db['sync_issues'])} sync issue(s)")
    facts["problems"] = problems
    facts["status"] = "PROBLEM" if problems else "OK"
    print(json.dumps(facts, indent=1))


if __name__ == "__main__":
    main()
