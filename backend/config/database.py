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

try:
    import pytds
except Exception:  # pragma: no cover - optional runtime fallback
    pytds = None

try:  # python-dotenv is a declared dependency; load backend/.env in source mode.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


class _PytdsCursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    def _normalize(self, sql, params):
        if not params:
            return sql, ()
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            normalized = tuple(params[0])
        else:
            normalized = tuple(params)
        if not normalized:
            return sql, ()
        return sql.replace("?", "%s"), normalized

    def execute(self, sql, *params):
        statement, normalized = self._normalize(sql, params)
        if not normalized:
            # pytds still runs %-formatting whenever a params argument is
            # passed, which blows up on literal '%' in the SQL (LIKE patterns,
            # etc). Omit the argument entirely for parameterless statements.
            return self._cursor.execute(statement)
        return self._cursor.execute(statement, normalized)

    def executemany(self, sql, params_seq):
        statement = sql.replace("?", "%s")
        normalized = [tuple(item) if isinstance(item, (list, tuple)) else item for item in params_seq]
        return self._cursor.executemany(statement, normalized)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PytdsConnectionAdapter:
    def __init__(self, connection):
        object.__setattr__(self, "_connection", connection)

    def cursor(self):
        return _PytdsCursorAdapter(self._connection.cursor())

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        # Without this, `conn.autocommit = True` would silently set the flag on
        # the adapter and leave the real connection in a transaction.
        setattr(self._connection, name, value)


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
    try:
        return pyodbc.connect(_connection_string())
    except pyodbc.Error:
        if pytds is None:
            raise
        auth_mode = os.getenv("DB_AUTH_MODE", "SQL").strip().upper()
        if auth_mode == "WINDOWS":
            return _PytdsConnectionAdapter(pytds.connect(
                dsn=os.getenv("DB_SERVER", "192.168.10.73"),
                database=os.getenv("DB_DATABASE", "NEXORA_PLATFORM"),
                use_sso=True,
            ))
        return _PytdsConnectionAdapter(pytds.connect(
            dsn=os.getenv("DB_SERVER", "192.168.10.73"),
            database=os.getenv("DB_DATABASE", "NEXORA_PLATFORM"),
            user=os.getenv("DB_USERNAME", "sa"),
            password=os.getenv("DB_PASSWORD", "Admin123"),
        ))
