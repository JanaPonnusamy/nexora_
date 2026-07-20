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


_RECOVERABLE_ACCESS = {"SINGLE_USER", "RESTRICTED_USER"}
_UNRECOVERABLE_STATES = {"RESTORING", "RECOVERING", "RECOVERY_PENDING", "SUSPECT", "OFFLINE"}


def _server_and_creds():
    return (
        _env("LEGACY_DB_SERVER", "DB_SERVER"),
        _env("LEGACY_DB_USERNAME", "DB_USERNAME"),
        _env("LEGACY_DB_PASSWORD", "DB_PASSWORD"),
    )


def _master_connection_string(server, username, password):
    return (
        f"DRIVER={{{_driver()}}};"
        f"SERVER={server};"
        "DATABASE=master;"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


def _try_recover_database(server, username, password, database):
    """Best-effort fix for a database stuck in SINGLE_USER/RESTRICTED_USER mode.

    OrderNMC periodically gets left in single-user mode by a maintenance
    session that never switched it back, which makes every other connection
    (including this API) fail. If that is the actual cause, clear the
    blocking session and flip it back to MULTI_USER so the request can just
    proceed instead of surfacing a raw 500. States like RESTORING/SUSPECT are
    left alone -- those need a DBA, not an auto-fix that could lose data.
    """
    try:
        admin_conn = pyodbc.connect(
            _master_connection_string(server, username, password), timeout=10, autocommit=True
        )
    except Exception:
        return False

    try:
        with _recovery_lock:
            cur = admin_conn.cursor()
            row = cur.execute(
                "SELECT state_desc, user_access_desc FROM sys.databases WHERE name = ?",
                database,
            ).fetchone()
            if not row:
                return False
            state_desc, user_access_desc = row

            if state_desc in _UNRECOVERABLE_STATES or state_desc == "EMERGENCY":
                _logger.error(
                    "Legacy database %s requires DBA recovery: state=%s access=%s",
                    database, state_desc, user_access_desc,
                )
                return False

            if user_access_desc in _RECOVERABLE_ACCESS:
                if not re.fullmatch(r"[A-Za-z0-9_. -]+", database):
                    return False
                quoted = f"[{database.replace(']', ']]')}]"
                cur.execute(f"ALTER DATABASE {quoted} SET MULTI_USER WITH ROLLBACK IMMEDIATE")
                return True

            return False
    except Exception:
        return False
    finally:
        admin_conn.close()


def get_central_connection(timeout=30):
    conn_string = central_connection_string()
    try:
        return pyodbc.connect(conn_string, timeout=timeout)
    except pyodbc.Error as initial_error:
        server, username, password = _server_and_creds()
        database = os.getenv("LEGACY_DB_DATABASE", "OrderNMC")
        if not _try_recover_database(server, username, password, database):
            state = _database_state(server, username, password, database)
            state_text = f" SQL Server reports state={state[0]}, access={state[1]}." if state else ""
            raise LegacyDatabaseUnavailable(
                f"Legacy database '{database}' is unavailable.{state_text} "
                "Check database files, disk space, the SQL Server error log, and login permissions."
            ) from initial_error
        try:
            return pyodbc.connect(conn_string, timeout=timeout)
        except pyodbc.Error as retry_error:
            raise LegacyDatabaseUnavailable(
                f"Legacy database '{database}' was returned to MULTI_USER, but still cannot be opened. "
                "Check the SQL Server error log and login permissions."
            ) from retry_error


def _database_state(server, username, password, database):
    """Read state through master without changing the database."""
    try:
        with pyodbc.connect(
            _master_connection_string(server, username, password), timeout=10
        ) as conn:
            row = conn.cursor().execute(
                "SELECT state_desc, user_access_desc FROM sys.databases WHERE name = ?",
                database,
            ).fetchone()
            return tuple(row) if row else None
    except Exception:
        return None


def get_branch_connection(server, database, username, password, timeout=30):
    return pyodbc.connect(
        branch_connection_string(server, database, username, password),
        timeout=timeout,
    )
