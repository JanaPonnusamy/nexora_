"""HO database connection.

Connection parameters resolve from environment variables so the SAME backend
works for any tenant. The HO installer writes them into ``config\\ho.env`` and
the Windows service loads that file before the app imports. The historical
development values remain as fallbacks, so running from source with no
configuration keeps behaving exactly as before.

Recognised variables (see backend/.env.example):
    DB_SERVER, DB_DATABASE, DB_DRIVER
    DB_AUTH_MODE = SQL | WINDOWS
    DB_USERNAME, DB_PASSWORD        (SQL auth only)
"""
import os

import pyodbc

try:  # python-dotenv is a declared dependency; load backend/.env in source mode.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


def _connection_string():
    server = os.getenv("DB_SERVER", "192.168.10.73")
    database = os.getenv("DB_DATABASE", "NEXORA_PLATFORM")
    driver = os.getenv("DB_DRIVER", _DEFAULT_DRIVER)
    auth_mode = os.getenv("DB_AUTH_MODE", "SQL").strip().upper()

    parts = [
        f"DRIVER={{{driver}}};",
        f"SERVER={server};",
        f"DATABASE={database};",
        "TrustServerCertificate=yes;",
    ]
    if auth_mode == "WINDOWS":
        parts.append("Trusted_Connection=yes;")
    else:
        parts.append(f"UID={os.getenv('DB_USERNAME', 'sa')};")
        parts.append(f"PWD={os.getenv('DB_PASSWORD', 'Admin123')};")
    return "".join(parts)


def get_connection():
    return pyodbc.connect(_connection_string())
