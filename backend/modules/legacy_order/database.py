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
import os

import pyodbc

try:  # python-dotenv is a declared dependency; load backend/.env in source mode.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


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


def get_central_connection(timeout=30):
    return pyodbc.connect(central_connection_string(), timeout=timeout)


def get_branch_connection(server, database, username, password, timeout=30):
    return pyodbc.connect(
        branch_connection_string(server, database, username, password),
        timeout=timeout,
    )
