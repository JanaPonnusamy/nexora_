"""Sync health monitor: watches every store's sync after each cycle and sends a
WhatsApp alert when something is wrong (silent when all good).

Why: the NMS Batches sync failed every 30 min for a month (2026-09-26 ->
2026-10-31, "src.ExpiryDate could not be bound") while dbo.sync_execution still
said COMPLETED -- nobody noticed until a Label Exporter user saw missing products.

Checks (per active store that has synced in the last 7 days):
  * TABLE_FAILING  - a table's last N attempts all FAILED (N = 2, so a one-off
                     blip does not page anyone)
  * TABLE_STALE    - a table has not COMPLETED for > 120 min (cycle is 30 min)
  * AGENT_OFFLINE  - no store-agent heartbeat for > 15 min
  * QUEUE_STUCK    - an execution sitting PENDING/RUNNING for > 60 min

Alerting is change-based: a new issue is sent once, an open issue is re-sent
every 6h, and a "resolved" line goes out when it clears. State lives in
dbo.sync_health_alert so several HO nodes running this backend never double-send
(a session sp_getapplock lets only one node evaluate per round). An issue is
only marked notified after WhatsApp reports "sent", so a node without a
logged-in WhatsApp session never swallows an alert.

Env: NEXORA_SYNC_MONITOR (1/0), NEXORA_SYNC_MONITOR_INTERVAL (seconds, 600),
NEXORA_SYNC_ALERT_PHONE (default: the default WhatsApp profile's default_phone).
"""

import logging
import os
import threading
import time
from datetime import datetime

from config.database import get_connection

logger = logging.getLogger("nexora.sync.health_monitor")

_ENABLED = os.getenv("NEXORA_SYNC_MONITOR", "1").strip().lower() not in ("0", "false", "no")
_INTERVAL = int(os.getenv("NEXORA_SYNC_MONITOR_INTERVAL", "600"))
_FAIL_STREAK = 2
_STALE_MINUTES = 120
_HEARTBEAT_MINUTES = 15
_STUCK_MINUTES = 60
_REMIND_HOURS = 6
_LOCK_NAME = "nexora_sync_health_monitor"

_started = False
_start_lock = threading.Lock()

_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.sync_health_alert', N'U') IS NULL
CREATE TABLE dbo.sync_health_alert (
    issue_key      NVARCHAR(300) NOT NULL PRIMARY KEY,
    store_code     NVARCHAR(50)  NULL,
    issue_type     NVARCHAR(30)  NOT NULL,
    detail         NVARCHAR(1000) NULL,
    first_seen     DATETIME NOT NULL DEFAULT GETDATE(),
    last_seen      DATETIME NOT NULL DEFAULT GETDATE(),
    last_notified  DATETIME NULL,
    resolved_at    DATETIME NULL
)
"""

# Active stores = is_active and synced in the last 7 days (skips retired/test
# stores that never sync, so they don't alert forever).
_STORES_SQL = """
SELECT s.store_id, s.store_code, hb.last_heartbeat
FROM dbo.stores s
OUTER APPLY (SELECT MAX(h.heartbeat_time) last_heartbeat FROM dbo.agent_heartbeat_log h
             WHERE h.store_id = s.store_id AND h.heartbeat_time >= DATEADD(DAY, -1, GETDATE())) hb
WHERE ISNULL(s.is_active, 1) = 1
  AND EXISTS (SELECT 1 FROM dbo.sync_execution_details d
              WHERE d.store_id = s.store_id AND d.created_at >= DATEADD(DAY, -7, GETDATE()))
"""

# Last few attempts per store/table (active tables only) + last success.
_TABLES_SQL = """
;WITH recent AS (
    SELECT d.store_id, d.table_name, d.status, d.error_message,
           ROW_NUMBER() OVER (PARTITION BY d.store_id, d.table_name ORDER BY d.created_at DESC) rn
    FROM dbo.sync_execution_details d
    WHERE d.created_at >= DATEADD(DAY, -7, GETDATE())
      AND d.status IN ('COMPLETED', 'FAILED')
      AND d.table_name IN (SELECT table_name FROM sync.sync_table_master WHERE is_active = 1)
)
SELECT r.store_id, r.table_name,
       SUM(CASE WHEN r.rn <= ? AND r.status = 'FAILED' THEN 1 ELSE 0 END) recent_fails,
       MAX(CASE WHEN r.rn = 1 THEN r.error_message END) last_error,
       (SELECT DATEDIFF(MINUTE, MAX(x.completed_at), GETDATE()) FROM dbo.sync_execution_details x
         WHERE x.store_id = r.store_id AND x.table_name = r.table_name AND x.status = 'COMPLETED') mins_since_ok
FROM recent r
GROUP BY r.store_id, r.table_name
"""

_STUCK_SQL = """
SELECT store_id, execution_status, DATEDIFF(MINUTE, ISNULL(started_at, scheduled_time), GETDATE()) age
FROM dbo.sync_execution
WHERE execution_status IN ('PENDING', 'RUNNING')
  AND ISNULL(started_at, scheduled_time) < DATEADD(MINUTE, -?, GETDATE())
"""


def _short(text, limit=140):
    # ODBC errors repeat a long "[Microsoft][ODBC Driver..][SQL Server]" prefix;
    # keep just the first SQL Server message.
    text = " ".join(str(text or "").split())
    if "[SQL Server]" in text:
        text = text.split("[SQL Server]", 1)[1].split(" (SQLExecDirectW)")[0]
    return text[:limit]


def collect_issues(cur):
    """Return {issue_key: (store_code, issue_type, detail)} for everything wrong now."""
    cur.execute(_STORES_SQL)
    stores = {str(r[0]).upper(): (r[1], r[2]) for r in cur.fetchall()}
    issues = {}
    now = datetime.now()

    for sid, (code, last_hb) in stores.items():
        if last_hb is None or (now - last_hb).total_seconds() > _HEARTBEAT_MINUTES * 60:
            seen = last_hb.strftime("%d/%m %H:%M") if last_hb else "never"
            issues[f"{sid}|AGENT"] = (code, "AGENT_OFFLINE", f"no agent heartbeat since {seen}")

    cur.execute(_TABLES_SQL, (_FAIL_STREAK,))
    for sid, table, fails, err, mins_ok in cur.fetchall():
        sid = str(sid).upper()
        if sid not in stores:
            continue
        code = stores[sid][0]
        if fails >= _FAIL_STREAK:
            issues[f"{sid}|{table}|FAIL"] = (code, "TABLE_FAILING", f"{table} failing: {_short(err)}")
        elif mins_ok is None or mins_ok > _STALE_MINUTES:
            age = "never" if mins_ok is None else f"{mins_ok // 60}h {mins_ok % 60}m ago"
            issues[f"{sid}|{table}|STALE"] = (code, "TABLE_STALE", f"{table} last synced OK {age}")

    cur.execute(_STUCK_SQL, (_STUCK_MINUTES,))
    for sid, status, age in cur.fetchall():
        sid = str(sid).upper()
        if sid in stores:
            issues[f"{sid}|QUEUE"] = (stores[sid][0], "QUEUE_STUCK", f"sync {status} for {age} min")
    return issues


def _alert_phone():
    phone = os.getenv("NEXORA_SYNC_ALERT_PHONE", "").strip()
    from modules.whatsapp import service as wa
    profiles = wa._load_profiles()
    if not profiles:
        return None, None
    profile = next((p for p in profiles if p.get("is_default")), profiles[0])
    return profile["profile_id"], phone or profile.get("default_phone", "")


def _send(lines):
    profile_id, phone = _alert_phone()
    if not profile_id or not phone:
        logger.warning("sync alert not sent (no WhatsApp profile/phone): %s", lines)
        return False
    from modules.whatsapp import service as wa
    try:
        result = wa.send_message(profile_id, phone, "\n".join(lines))
    except Exception:
        logger.exception("sync alert WhatsApp send failed")
        return False
    ok = (result or {}).get("status") == "sent"
    if not ok:
        logger.warning("sync alert WhatsApp send not confirmed: %s", result)
    return ok


def run_once(notify=True):
    """One evaluation round. Returns a summary dict (also used by the API)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SCHEMA_SQL)
        conn.commit()
        cur.execute("DECLARE @r INT; EXEC @r = sp_getapplock @Resource=?, @LockMode='Exclusive', "
                    "@LockOwner='Session', @LockTimeout=0; SELECT @r;", (_LOCK_NAME,))
        got = cur.fetchone()[0]
        if got is None or got < 0:
            return {"skipped": "another HO node is evaluating"}
        try:
            return _evaluate(conn, cur, notify)
        finally:
            cur.execute("EXEC sp_releaseapplock @Resource=?, @LockOwner='Session'", (_LOCK_NAME,))
            conn.commit()
    finally:
        conn.close()


def _evaluate(conn, cur, notify):
    issues = collect_issues(cur)
    cur.execute("SELECT issue_key, store_code, issue_type, detail, last_notified FROM dbo.sync_health_alert "
                "WHERE resolved_at IS NULL")
    open_rows = {r[0]: r for r in cur.fetchall()}
    now = datetime.now()

    for key, (code, itype, detail) in issues.items():
        if key in open_rows:
            cur.execute("UPDATE dbo.sync_health_alert SET last_seen=GETDATE(), detail=? WHERE issue_key=?",
                        (detail, key))
        else:
            cur.execute("DELETE FROM dbo.sync_health_alert WHERE issue_key=?", (key,))
            cur.execute("INSERT INTO dbo.sync_health_alert (issue_key, store_code, issue_type, detail) "
                        "VALUES (?, ?, ?, ?)", (key, code, itype, detail))
    resolved = [open_rows[k] for k in open_rows if k not in issues]
    for row in resolved:
        cur.execute("UPDATE dbo.sync_health_alert SET resolved_at=GETDATE() WHERE issue_key=?", (row[0],))
    conn.commit()

    # What to announce: never-notified issues, issues due a reminder, and
    # resolutions of issues we had actually announced.
    due = []
    for key, (code, itype, detail) in issues.items():
        last = open_rows[key][4] if key in open_rows else None
        if last is None or (now - last).total_seconds() >= _REMIND_HOURS * 3600:
            due.append((key, code, detail, last is not None))
    announced_resolved = [r for r in resolved if r[4] is not None]

    sent = False
    if notify and (due or announced_resolved):
        lines = ["NEXORA SYNC ALERT " + now.strftime("%d/%m %H:%M")]
        for _, code, detail, reminder in sorted(due, key=lambda d: (d[1] or "", d[2])):
            lines.append(f"- {code}: {detail}" + (" (still open)" if reminder else ""))
        if announced_resolved:
            lines.append("Resolved:")
            lines += [f"- {r[1]}: {r[3]}" for r in announced_resolved]
        if not due:
            lines.append("All stores syncing OK now.")
        sent = _send(lines)
        if sent and due:
            for key, *_ in due:
                cur.execute("UPDATE dbo.sync_health_alert SET last_notified=GETDATE() WHERE issue_key=?", (key,))
            conn.commit()

    return {
        "checked_at": now.isoformat(timespec="seconds"),
        "all_good": not issues,
        "issues": [{"store": c, "type": t, "detail": d} for c, t, d in issues.values()],
        "resolved": [{"store": r[1], "detail": r[3]} for r in resolved],
        "notified": sent,
    }


def current_status():
    """Read-only snapshot for the API -- evaluates checks, touches no alert state."""
    conn = get_connection()
    try:
        issues = collect_issues(conn.cursor())
    finally:
        conn.close()
    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "all_good": not issues,
        "issues": [{"store": c, "type": t, "detail": d} for c, t, d in issues.values()],
    }


def _loop(interval):
    time.sleep(60)  # let the backend finish starting / WhatsApp warm up
    while True:
        try:
            summary = run_once()
            if summary.get("issues"):
                logger.warning("sync health: %d issue(s)", len(summary["issues"]))
        except Exception:
            logger.exception("sync health monitor iteration failed")
        time.sleep(interval)


def start_background_loop(interval_seconds=None):
    global _started
    if not _ENABLED:
        return
    with _start_lock:
        if _started:
            return
        _started = True
    interval = _INTERVAL if interval_seconds is None else interval_seconds
    threading.Thread(target=_loop, args=(interval,), name="sync-health-monitor", daemon=True).start()
    logger.info("sync health monitor started (every %ss)", interval)
