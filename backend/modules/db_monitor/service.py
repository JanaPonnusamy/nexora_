"""Live Queries / Repair: read SQL Server's own activity view (sys.dm_exec_
requests/sessions/sql_text) and let an admin kill a stuck session.

Root cause this exists for (owner report 2026-11-24): store sync, order
process, and qty-check/fetch-order-products queries all run on independent
threads per store (modules.legacy_order.service -- confirmed PARALLEL, not
first-come-first-served; see that module's docstring), so several heavy,
unbounded queries can land on the SAME central OrderNMC database at the same
time. Some of those queries scan/aggregate full tables (ProductSaleInformation,
PurchaseTrans) with no row cap and no client-side statement timeout, so under
concurrent load SQL Server Express's capped buffer pool thrashes and sessions
deadlock (1205) or just run for a very long time holding locks. This module is
the admin's way to SEE that happening and kill the offending session instead
of restarting the whole backend.

Targets the SAME database every store action hits (central OrderNMC via
modules.legacy_order.database.get_central_connection) -- this is deliberately
NOT scoped per tenant/store; an admin needs to see everything contending on
that one server at once, including rows from app connections this module
itself doesn't own.
"""
from __future__ import annotations

import logging

import pyodbc

from modules.legacy_order import database

logger = logging.getLogger(__name__)

# sys.dm_exec_requests only has a row per currently-EXECUTING request; a session
# that is open but idle (connection sitting in a pool, or between statements)
# does not show up here, which is deliberately what we want -- this page is for
# "what is running right now", not a full connection census.
_ACTIVE_REQUESTS_SQL = """
SELECT
    r.session_id,
    r.status,
    r.command,
    r.wait_type,
    r.wait_time,
    r.blocking_session_id,
    r.cpu_time,
    r.total_elapsed_time,
    r.reads,
    r.writes,
    r.logical_reads,
    r.row_count,
    r.start_time,
    s.login_name,
    s.host_name,
    s.program_name,
    DB_NAME(r.database_id) AS database_name,
    t.text AS query_text
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.session_id <> @@SPID
ORDER BY r.total_elapsed_time DESC;
"""

# A broader view for completeness/debugging: every session SQL Server
# currently knows about (includes idle app-pool connections), paired with its
# active request if any. Separate from the main list (which should stay
# focused on "what's actually running") so the UI can offer it as a toggle.
_ALL_SESSIONS_SQL = """
SELECT
    s.session_id,
    s.status,
    s.login_name,
    s.host_name,
    s.program_name,
    DB_NAME(s.database_id) AS database_name,
    s.last_request_start_time,
    s.last_request_end_time,
    r.total_elapsed_time,
    r.blocking_session_id,
    r.wait_type
FROM sys.dm_exec_sessions s
LEFT JOIN sys.dm_exec_requests r ON r.session_id = s.session_id
WHERE s.is_user_process = 1 AND s.session_id <> @@SPID
ORDER BY s.last_request_start_time DESC;
"""


def _row_to_request(row):
    return {
        "session_id": row.session_id,
        "status": row.status,
        "command": row.command,
        "wait_type": row.wait_type,
        "wait_time_ms": row.wait_time,
        "blocking_session_id": row.blocking_session_id or None,
        "cpu_time_ms": row.cpu_time,
        "total_elapsed_ms": row.total_elapsed_time,
        "reads": row.reads,
        "writes": row.writes,
        "logical_reads": row.logical_reads,
        "row_count": row.row_count,
        "start_time": row.start_time,
        "login_name": (row.login_name or "").strip(),
        "host_name": (row.host_name or "").strip(),
        "program_name": (row.program_name or "").strip(),
        "database_name": row.database_name,
        "query_text": (row.query_text or "").strip(),
    }


def _row_to_session(row):
    return {
        "session_id": row.session_id,
        "status": row.status,
        "login_name": (row.login_name or "").strip(),
        "host_name": (row.host_name or "").strip(),
        "program_name": (row.program_name or "").strip(),
        "database_name": row.database_name,
        "last_request_start_time": row.last_request_start_time,
        "last_request_end_time": row.last_request_end_time,
        "total_elapsed_ms": row.total_elapsed_time,
        "blocking_session_id": row.blocking_session_id or None,
        "wait_type": row.wait_type,
    }


def active_requests():
    """Currently-executing requests, longest-running first."""
    with database.get_central_connection(timeout=10) as conn:
        rows = conn.cursor().execute(_ACTIVE_REQUESTS_SQL).fetchall()
    return [_row_to_request(r) for r in rows]


def all_sessions():
    """Every user session (including idle), for the 'show everything' toggle."""
    with database.get_central_connection(timeout=10) as conn:
        rows = conn.cursor().execute(_ALL_SESSIONS_SQL).fetchall()
    return [_row_to_session(r) for r in rows]


class InvalidSessionId(ValueError):
    """session_id is not a positive integer -- refuse to format it into KILL."""


def kill_session(session_id, actor=None):
    """KILL <session_id>. session_id must already be an int (FastAPI's path/
    body validation on the caller's Pydantic model does that) -- re-validated
    here too since KILL takes no parameter placeholder in T-SQL and the value
    must be interpolated directly into the statement text."""
    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        raise InvalidSessionId("session_id must be an integer.") from None
    if session_id <= 0:
        raise InvalidSessionId("session_id must be a positive integer.")
    logger.warning("[DB_MONITOR] KILL %s requested by %s", session_id, actor)
    # KILL is not valid inside a user transaction -- autocommit=True on this
    # connection (get_central_connection's default pyodbc.connect is NOT
    # autocommit, and `with conn:` would wrap the statement in one).
    conn = pyodbc.connect(database.central_connection_string(), timeout=10, autocommit=True)
    try:
        try:
            conn.cursor().execute(f"KILL {session_id}")
        except Exception as exc:
            # SQL Server raises if the session already ended, is a system
            # session, or can't be killed right now (e.g. mid-rollback) --
            # surface that message rather than a bare exception.
            raise ValueError(str(exc)) from exc
    finally:
        conn.close()
    return {"session_id": session_id, "killed": True}
