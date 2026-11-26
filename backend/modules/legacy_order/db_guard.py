"""Database guard (owner request 2026-11-27): keep every database this HO
depends on ONLINE / MULTI_USER without anyone running a repair by hand, and
tell the desktop clients when they are under maintenance.

Every CHECK_SECONDS it reads sys.databases (through master, so a broken
database does not stop the check) for NEXORA_PLATFORM and each tenant's
legacy database (OrderNMC / OrderSMS / ...), and for any that is not
ONLINE / MULTI_USER runs database.recover_database(allow_data_loss=False):

  SINGLE_USER / RESTRICTED_USER -> SET MULTI_USER
  EMERGENCY                     -> SET ONLINE (re-runs recovery)
  RECOVERY_PENDING / SUSPECT    -> SET OFFLINE + SET ONLINE (crash recovery)

and turns AUTO_CLOSE off on each database it watches (AUTO_CLOSE ON was the
real cause of the recurring RECOVERY_PENDING on .73: SQL drops the file handle
and something else grabs the .mdf). RESTORING / RECOVERING are never touched.

DBCC CHECKDB REPAIR_ALLOW_DATA_LOSS is NOT automatic -- it can delete data;
when the safe ladder does not bring a database back, the guard sends a
WhatsApp alert (the sync health monitor's number) and keeps retrying the safe
ladder; the Legacy Order console's Emergency Repair stays the manual step.

status() feeds the unauthenticated GET /health/maintenance the Stock Client
and MediQ poll to show their "under maintenance" screen.

Env:
  NEXORA_DB_GUARD_DISABLED=1   don't start the loop
"""
from __future__ import annotations

import datetime
import logging
import os
import threading
import time

import pyodbc

from modules.legacy_order import database

logger = logging.getLogger(__name__)

CHECK_SECONDS = 60
# While a database is broken, check it this often instead.
REPAIR_RETRY_SECONDS = 30
ALERT_EVERY_SECONDS = 30 * 60

_status: dict = {"checked_at": None, "sql_reachable": None, "databases": [], "repairing": None}
_lock = threading.Lock()
_auto_close_done: set = set()
_last_alert: dict = {}
_started = False


def _platform_db():
    return os.getenv("DB_DATABASE", "NEXORA_PLATFORM")


def watched_databases():
    """[(name, role)] -- the platform DB plus every tenant's legacy DB."""
    out = [(_platform_db(), "platform")]
    try:
        from modules.legacy_order import morning_order

        for t in morning_order.tenants():
            out.append((t["database"], "legacy"))
    except Exception:  # platform DB down: still watch the default legacy DB
        out.append((os.getenv("LEGACY_DB_DATABASE", "OrderNMC"), "legacy"))
    seen, unique = set(), []
    for name, role in out:
        if name and name.upper() not in seen:
            seen.add(name.upper())
            unique.append((name, role))
    return unique


def _master():
    server, username, password = database._server_and_creds()
    return pyodbc.connect(database._master_connection_string(server, username, password),
                          timeout=10, autocommit=True)


def _read_all(names):
    """{NAME: (state, access, auto_close)} for the named databases."""
    with _master() as conn:
        marks = ",".join("?" for _ in names)
        rows = conn.cursor().execute(
            f"SELECT name, state_desc, user_access_desc, is_auto_close_on FROM sys.databases WHERE name IN ({marks})",
            *names,
        ).fetchall()
    return {r[0].upper(): (r[1], r[2], bool(r[3])) for r in rows}


def _auto_close_off(name):
    if name.upper() in _auto_close_done or not database._valid_db_name(name):
        return
    try:
        with _master() as conn:
            conn.cursor().execute(f"ALTER DATABASE {database._quoted(name)} SET AUTO_CLOSE OFF WITH NO_WAIT")
        _auto_close_done.add(name.upper())
        logger.info("[DB_GUARD] AUTO_CLOSE turned off on %s", name)
    except Exception:
        logger.warning("[DB_GUARD] could not turn AUTO_CLOSE off on %s", name, exc_info=True)


def _alert(name, message):
    now = time.monotonic()
    if now - _last_alert.get(name.upper(), -ALERT_EVERY_SECONDS) < ALERT_EVERY_SECONDS:
        return
    _last_alert[name.upper()] = now
    try:
        from modules.sync import health_monitor

        health_monitor._send([
            f"⚠️ HO database {name} needs attention",
            message,
            "Safe auto-repair keeps retrying. A data-loss repair (Emergency Repair) is manual only.",
        ])
    except Exception:
        logger.exception("[DB_GUARD] alert send failed for %s", name)


def check_once():
    """One pass: read, repair what is broken, refresh status(). Returns the
    status dict."""
    now = datetime.datetime.now()
    watched = watched_databases()
    entries = []
    try:
        states = _read_all([n for n, _ in watched])
        reachable = True
    except Exception as exc:
        reachable = False
        states = {}
        reason = database._short_error(exc)
        logger.warning("[DB_GUARD] SQL Server unreachable: %s", reason)
        with _lock:
            _status.update(checked_at=now.isoformat(timespec="seconds"), sql_reachable=False,
                           sql_error=reason, repairing=None,
                           databases=[{"name": n, "role": r, "ok": False, "state": None, "access": None,
                                       "message": "SQL Server unreachable"} for n, r in watched])
            return dict(_status)
    for name, role in watched:
        state, access, auto_close = states.get(name.upper(), (None, None, False))
        entry = {"name": name, "role": role, "state": state, "access": access,
                 "ok": state == "ONLINE" and access == "MULTI_USER", "message": ""}
        if state is None:
            entry["message"] = "not found on this SQL Server"
            entry["ok"] = role == "legacy"  # an unused tenant mapping is not an outage
        elif not entry["ok"] and state not in database._DBA_ONLY_STATES:
            with _lock:
                _status["repairing"] = name
            token = database.set_active_tenant(None)
            try:
                result = database.recover_database(allow_data_loss=False, database=name)
            except Exception as exc:
                result = {"ok": False, "message": str(exc)}
            finally:
                database.reset_active_tenant(token)
            after = result.get("after") or {}
            entry.update(state=after.get("state") or state, access=after.get("access") or access,
                         ok=bool(result.get("ok")), message=result.get("message") or "",
                         repaired_at=now.isoformat(timespec="seconds"))
            logger.warning("[DB_GUARD] %s was %s/%s: %s", name, state, access, entry["message"])
            if not entry["ok"]:
                _alert(name, f"{name} is {entry['state']} / {entry['access']}. {entry['message']}")
        elif state in database._DBA_ONLY_STATES:
            entry["message"] = f"{state}: a restore/recovery is running -- left alone"
        if state == "ONLINE" and auto_close:
            _auto_close_off(name)
        entries.append(entry)
    with _lock:
        _status.update(checked_at=now.isoformat(timespec="seconds"), sql_reachable=reachable,
                       sql_error=None, databases=entries, repairing=None)
        return dict(_status)


def status():
    """What the clients' maintenance screen shows. maintenance=True when the
    HO cannot serve data: SQL Server unreachable, the platform DB down, or a
    repair running. Legacy DBs down are listed (the client decides whether
    its own tenant is affected)."""
    with _lock:
        s = dict(_status)
    dbs = s.get("databases") or []
    down = [d for d in dbs if not d.get("ok")]
    platform_down = any(d["role"] == "platform" for d in down)
    if s.get("sql_reachable") is False:
        reason = "database_unreachable"
        message = "Working on connecting to the database server."
    elif s.get("repairing"):
        reason = "database_repair"
        message = f"Database {s['repairing']} is being repaired automatically."
    elif platform_down:
        d = next(d for d in down if d["role"] == "platform")
        reason = "database_repair"
        message = f"Database {d['name']} is {d.get('state')} -- automatic repair in progress."
    else:
        reason, message = None, None
    return {
        "status": "maintenance" if reason else "ok",
        "maintenance": bool(reason),
        "reason": reason,
        "message": message,
        "checked_at": s.get("checked_at"),
        "databases": [{k: d.get(k) for k in ("name", "role", "state", "access", "ok", "message")} for d in dbs],
        "legacy_down": [d["name"] for d in down if d["role"] == "legacy"],
    }


def _loop():
    time.sleep(20)
    while True:
        delay = CHECK_SECONDS
        try:
            s = check_once()
            if not s.get("sql_reachable") or any(not d.get("ok") for d in s.get("databases") or []):
                delay = REPAIR_RETRY_SECONDS
        except Exception:
            logger.exception("[DB_GUARD] check failed")
        time.sleep(delay)


def start_background_loop():
    global _started
    if os.getenv("NEXORA_DB_GUARD_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return False
    if _started:
        return False
    _started = True
    threading.Thread(target=_loop, name="db-guard", daemon=True).start()
    print("[DB_GUARD] database guard started (auto-repair RECOVERY_PENDING / SUSPECT / EMERGENCY / SINGLE_USER)")
    return True
