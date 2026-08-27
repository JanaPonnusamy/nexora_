"""Connections for the legacy Order console.

This module deliberately does NOT use ``config.database`` (NEXORA_PLATFORM).
Everything here targets the OLD OrderNMC database and the branch SQL Servers it
points at, exactly like the legacy VB.NET app did.

Credentials are never hardcoded. OrderNMC normally lives on the same SQL Server
instance as NEXORA_PLATFORM, so by default the server/user/password are inherited
from the existing DB_* variables in backend/.env and only the database name
differs. Point the console at a different host by setting the LEGACY_DB_*
overrides:

    LEGACY_DB_SERVER, LEGACY_DB_DATABASE (default: OrderNMC), LEGACY_DB_DRIVER
    LEGACY_DB_USERNAME, LEGACY_DB_PASSWORD

Branch credentials are not configuration at all -- they are read per store from
OrderNMC's own dbo.Stores table, which is where the VB app kept them.
"""
import logging
import os
import re
import threading

import pyodbc

try:  # python-dotenv is a declared dependency; load backend/.env in source mode.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
_logger = logging.getLogger(__name__)
_recovery_lock = threading.Lock()


class LegacyDatabaseUnavailable(ConnectionError):
    """The legacy database could not be opened or safely recovered."""


def _env(name, fallback_name, default=None):
    """LEGACY_DB_* wins; otherwise inherit the platform's DB_* setting."""
    return os.getenv(name) or os.getenv(fallback_name) or default


def _driver():
    return _env("LEGACY_DB_DRIVER", "DB_DRIVER", _DEFAULT_DRIVER)


def central_connection_string():
    """Connection string for the central OrderNMC database."""
    server = _env("LEGACY_DB_SERVER", "DB_SERVER")
    username = _env("LEGACY_DB_USERNAME", "DB_USERNAME")
    password = _env("LEGACY_DB_PASSWORD", "DB_PASSWORD")
    database = os.getenv("LEGACY_DB_DATABASE", "OrderNMC")

    missing = [
        name
        for name, value in (
            ("LEGACY_DB_SERVER / DB_SERVER", server),
            ("LEGACY_DB_USERNAME / DB_USERNAME", username),
            ("LEGACY_DB_PASSWORD / DB_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Legacy Order console is not configured: missing "
            + ", ".join(missing)
            + ". Set them in backend/.env."
        )

    return (
        f"DRIVER={{{_driver()}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


def branch_connection_string(server, database, username, password):
    """Connection string for a branch store, built from dbo.Stores columns."""
    return (
        f"DRIVER={{{_driver()}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


# Access modes we can safely flip back to MULTI_USER without a DBA.
_RECOVERABLE_ACCESS = {"SINGLE_USER", "RESTRICTED_USER"}
# A genuine restore/recovery is in progress -- interrupting it can destroy the
# database. Never touch these, not even with an explicit repair request.
_DBA_ONLY_STATES = {"RESTORING", "RECOVERING"}
# States a non-destructive restart (offline/online) can clear, and that an
# explicit emergency repair can attack with REPAIR_ALLOW_DATA_LOSS.
_REPAIRABLE_STATES = {"RECOVERY_PENDING", "SUSPECT"}
# EMERGENCY is entered manually -- typically as the first step of a corruption
# repair. A database can get stuck here if an emergency repair was interrupted
# or never ran its final SET ONLINE. Leaving it is non-destructive: SET ONLINE
# simply re-runs crash recovery.
_EMERGENCY_STATE = "EMERGENCY"


def _server_and_creds():
    return (
        _env("LEGACY_DB_SERVER", "DB_SERVER"),
        _env("LEGACY_DB_USERNAME", "DB_USERNAME"),
        _env("LEGACY_DB_PASSWORD", "DB_PASSWORD"),
    )


def _database_name():
    return os.getenv("LEGACY_DB_DATABASE", "OrderNMC")


def _master_connection_string(server, username, password):
    return (
        f"DRIVER={{{_driver()}}};"
        f"SERVER={server};"
        "DATABASE=master;"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


def _valid_db_name(database):
    return bool(database and re.fullmatch(r"[A-Za-z0-9_. -]+", database))


def _quoted(database):
    return f"[{database.replace(']', ']]')}]"


def _read_state(cur, database):
    row = cur.execute(
        "SELECT state_desc, user_access_desc FROM sys.databases WHERE name = ?",
        database,
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def database_health():
    """State of the legacy database, read through master without changing it.

    Powers the console's DB status card and its Recheck button.
    """
    server, username, password = _server_and_creds()
    database = _database_name()
    result = {
        "database": database,
        "server": server,
        "reachable": False,
        "state": None,
        "access": None,
        "online": False,
        "message": "",
    }
    try:
        conn = pyodbc.connect(
            _master_connection_string(server, username, password), timeout=10
        )
    except Exception as exc:
        result["message"] = f"Cannot reach SQL Server: {_short_error(exc)}"
        return result
    try:
        state, access = _read_state(conn.cursor(), database)
        result.update(reachable=True, state=state, access=access)
        result["online"] = state == "ONLINE" and access == "MULTI_USER"
        if state is None:
            result["message"] = f"Database '{database}' was not found on this server."
        elif result["online"]:
            result["message"] = "Database is ONLINE and MULTI_USER."
        else:
            result["message"] = f"Database is {state} / {access}."
    finally:
        conn.close()
    return result


def _short_error(exc):
    text = str(exc).strip()
    return text.splitlines()[-1] if text else exc.__class__.__name__


def recover_database(allow_data_loss=False):
    """Walk a database back to ONLINE / MULTI_USER, escalating only as needed.

    The ladder, safest first:

    1. ONLINE but SINGLE_USER/RESTRICTED_USER -> flip to MULTI_USER (a stuck
       maintenance session; the common case).
    2. RECOVERY_PENDING / SUSPECT -> a clean OFFLINE then ONLINE re-runs crash
       recovery. This is non-destructive: if the log is intact it just works.
    3. Still broken and ``allow_data_loss`` -> EMERGENCY + SINGLE_USER +
       ``DBCC CHECKDB REPAIR_ALLOW_DATA_LOSS`` + MULTI_USER. This CAN lose data,
       so it only runs for the explicit Emergency Repair action, never
       automatically.

    Restores in progress (RESTORING/RECOVERING) are always left alone. Returns
    a structured report the UI renders step by step.
    """
    server, username, password = _server_and_creds()
    database = _database_name()
    steps = []

    def log(action, ok, detail=""):
        steps.append({"action": action, "ok": ok, "detail": detail})

    if not _valid_db_name(database):
        return {
            "ok": False, "database": database, "steps": steps,
            "message": "Refusing to operate on an unsafe database name.",
        }
    quoted = _quoted(database)

    try:
        admin = pyodbc.connect(
            _master_connection_string(server, username, password),
            timeout=15, autocommit=True,
        )
    except Exception as exc:
        return {
            "ok": False, "database": database, "steps": steps,
            "message": f"Cannot reach SQL Server: {_short_error(exc)}",
        }

    before = {"state": None, "access": None}
    after = {"state": None, "access": None}
    try:
        with _recovery_lock:
            cur = admin.cursor()
            state, access = _read_state(cur, database)
            before = {"state": state, "access": access}

            if state is None:
                return {
                    "ok": False, "database": database, "before": before,
                    "steps": steps, "message": f"Database '{database}' was not found.",
                }
            if state in _DBA_ONLY_STATES:
                log(f"detect {state}", False, "A restore/recovery is in progress.")
                return {
                    "ok": False, "database": database, "before": before,
                    "after": before, "steps": steps,
                    "message": f"Database is {state}; a restore is in progress. Left untouched.",
                }

            def run(action, sql):
                try:
                    cur.execute(sql)
                    log(action, True)
                    return True
                except Exception as exc:
                    log(action, False, _short_error(exc))
                    return False

            # 1. Access-only problem: ONLINE but not MULTI_USER.
            if state == "ONLINE" and access in _RECOVERABLE_ACCESS:
                run("SET MULTI_USER", f"ALTER DATABASE {quoted} SET MULTI_USER WITH ROLLBACK IMMEDIATE")
                state, access = _read_state(cur, database)

            # 1b. EMERGENCY: usually left over from an interrupted emergency
            # repair (or a manual SET EMERGENCY). SET ONLINE is non-destructive
            # -- it just re-runs recovery; if the files are intact it comes
            # straight back ONLINE. This is the common "stuck in emergency" case.
            if state == _EMERGENCY_STATE:
                run("SET ONLINE", f"ALTER DATABASE {quoted} SET ONLINE")
                state, access = _read_state(cur, database)

            # 2. RECOVERY_PENDING / SUSPECT: non-destructive restart of recovery.
            if state in _REPAIRABLE_STATES:
                if run("SET OFFLINE", f"ALTER DATABASE {quoted} SET OFFLINE WITH ROLLBACK IMMEDIATE"):
                    run("SET ONLINE", f"ALTER DATABASE {quoted} SET ONLINE")
                state, access = _read_state(cur, database)

            # 3. Still broken: emergency repair, only with explicit consent.
            if state in _REPAIRABLE_STATES or state == _EMERGENCY_STATE:
                if allow_data_loss:
                    run("SET EMERGENCY", f"ALTER DATABASE {quoted} SET EMERGENCY")
                    run("SET SINGLE_USER", f"ALTER DATABASE {quoted} SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
                    run(
                        "DBCC CHECKDB REPAIR_ALLOW_DATA_LOSS",
                        f"DBCC CHECKDB ({quoted}, REPAIR_ALLOW_DATA_LOSS) WITH NO_INFOMSGS, ALL_ERRORMSGS",
                    )
                    # A repaired database is still in EMERGENCY until SET ONLINE
                    # re-runs recovery -- without this it stays EMERGENCY forever.
                    run("SET ONLINE", f"ALTER DATABASE {quoted} SET ONLINE")
                    run("SET MULTI_USER", f"ALTER DATABASE {quoted} SET MULTI_USER")
                    state, access = _read_state(cur, database)
                else:
                    log("emergency repair", False, "Skipped: needs explicit confirmation (data loss possible).")

            # Ensure we did not leave it single-user after a repair.
            if state == "ONLINE" and access in _RECOVERABLE_ACCESS:
                run("SET MULTI_USER", f"ALTER DATABASE {quoted} SET MULTI_USER WITH ROLLBACK IMMEDIATE")
                state, access = _read_state(cur, database)

            after = {"state": state, "access": access}
    finally:
        admin.close()

    # Confirm with a real application connection.
    connected = False
    try:
        pyodbc.connect(central_connection_string(), timeout=15).close()
        connected = True
    except Exception:
        connected = False

    ok = connected and after.get("state") == "ONLINE"
    if ok:
        message = f"Recovered: database is {after['state']} / {after['access']}."
    elif after.get("state") in (_REPAIRABLE_STATES | {_EMERGENCY_STATE}) and not allow_data_loss:
        message = (
            f"Database is still {after['state']}. The non-destructive restart did not clear it -- "
            "run Emergency Repair (may lose data) or call a DBA."
        )
    else:
        message = f"Recovery incomplete: database is {after.get('state')} / {after.get('access')}."

    _logger.info("Legacy DB recovery (allow_data_loss=%s): %s -> %s | %s",
                 allow_data_loss, before, after, message)
    return {
        "ok": ok, "database": database, "before": before, "after": after,
        "connected": connected, "steps": steps, "message": message,
    }


def get_central_connection(timeout=30):
    conn_string = central_connection_string()
    try:
        return pyodbc.connect(conn_string, timeout=timeout)
    except pyodbc.Error as initial_error:
        # Best-effort NON-DESTRUCTIVE auto-recovery: a single-user flip, or a
        # clean offline/online restart for RECOVERY_PENDING/SUSPECT. Data-loss
        # repair is never automatic -- that is the explicit Emergency Repair
        # button only.
        result = recover_database(allow_data_loss=False)
        if result.get("connected"):
            try:
                return pyodbc.connect(conn_string, timeout=timeout)
            except pyodbc.Error:
                pass
        database = _database_name()
        after = result.get("after") or {}
        state_text = ""
        if after.get("state"):
            state_text = f" SQL Server reports state={after['state']}, access={after['access']}."
        raise LegacyDatabaseUnavailable(
            f"Legacy database '{database}' is unavailable.{state_text} "
            "Check database files, disk space, the SQL Server error log, and login permissions."
        ) from initial_error


def get_branch_connection(server, database, username, password, timeout=30):
    return pyodbc.connect(
        branch_connection_string(server, database, username, password),
        timeout=timeout,
    )
