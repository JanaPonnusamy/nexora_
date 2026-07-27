"""Connection to the Matrix COSEC attendance database.

This is a genuinely separate SQL Server instance from NEXORA_PLATFORM -- its
own box, its own login -- so (unlike modules/legacy_order/database.py, whose
OrderNMC DB normally shares the platform server) there is no fallback to the
platform DB_* variables. All of COSEC_DB_SERVER / DATABASE / USERNAME /
PASSWORD must be set in backend/.env for this module to work.
"""
import os

import pyodbc

try:  # python-dotenv is a declared dependency; load backend/.env in source mode.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


class TimeReportDatabaseUnavailable(ConnectionError):
    """COSEC could not be reached -- misconfiguration or the box is down."""


def _connection_string():
    server = os.getenv("COSEC_DB_SERVER")
    database = os.getenv("COSEC_DB_DATABASE", "COSEC")
    username = os.getenv("COSEC_DB_USERNAME")
    password = os.getenv("COSEC_DB_PASSWORD")
    driver = os.getenv("COSEC_DB_DRIVER", _DEFAULT_DRIVER)

    missing = [
        name
        for name, value in (
            ("COSEC_DB_SERVER", server),
            ("COSEC_DB_USERNAME", username),
            ("COSEC_DB_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Time Report module is not configured: missing "
            + ", ".join(missing)
            + ". Set them in backend/.env."
        )

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


def get_connection(timeout=15):
    """Open a fresh connection to COSEC. Callers are responsible for closing it."""
    try:
        return pyodbc.connect(_connection_string(), timeout=timeout)
    except pyodbc.Error as exc:
        raise TimeReportDatabaseUnavailable(
            "Could not reach the COSEC attendance database. "
            "Check COSEC_DB_SERVER/DATABASE/USERNAME/PASSWORD in backend/.env "
            "and that the SQL Server instance is reachable."
        ) from exc
