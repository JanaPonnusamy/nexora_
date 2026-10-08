"""JSON (de)serialization helpers for the sync wire format.

Rows coming out of pyodbc carry Decimal / datetime / bytes that the default JSON
encoder cannot handle; rows coming in from the agent carry ISO date strings that
need to go back to datetimes before they hit a typed staging column. Both
directions are centralised here so the wire format stays consistent.
"""
from __future__ import annotations

import datetime
import decimal


def to_jsonable(value):
    """Convert a single pyodbc cell value to a JSON-serialisable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        # str(), not float(): preserves exact money/qty scale on the wire.
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, uuid_type()):
        return str(value)
    return str(value)


def uuid_type():
    import uuid
    return uuid.UUID


def row_to_dict(columns, row):
    """A single cursor row -> JSON-safe dict keyed by column name."""
    return {col: to_jsonable(row[i]) for i, col in enumerate(columns)}


def rows_to_dicts(cursor):
    columns = [c[0] for c in cursor.description]
    return [row_to_dict(columns, row) for row in cursor.fetchall()]


# ---- inbound coercion -----------------------------------------------------

_ISO_DATE_LEN = len("YYYY-MM-DD")


def coerce_inbound(value, sql_type: str | None):
    """Coerce one JSON value toward the destination SQL type.

    pyodbc + SQL Server implicitly convert most NVARCHAR inputs, but datetimes
    sent as ISO strings bind more reliably as real datetime objects. sql_type is
    the INFORMATION_SCHEMA.DATA_TYPE of the destination column (lower-cased), or
    None when unknown (then the value is passed through untouched).
    """
    if value is None:
        return None
    t = (sql_type or "").lower()
    if t in ("datetime", "datetime2", "smalldatetime", "date") and isinstance(value, str):
        parsed = _parse_iso(value)
        if parsed is not None:
            return parsed
    if t == "bit" and isinstance(value, bool):
        return 1 if value else 0
    return value


def _parse_iso(text: str):
    text = text.strip()
    if not text:
        return None
    try:
        if len(text) == _ISO_DATE_LEN:
            return datetime.date.fromisoformat(text)
        # Python's fromisoformat is picky about trailing 'Z'; normalise it.
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
