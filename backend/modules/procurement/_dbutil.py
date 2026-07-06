"""Shared data-access helpers for the Procurement repositories.

Small, pure utilities that were previously duplicated in every repository.
Kept dependency-free so any repository can import them without cycles.
"""

import uuid


def as_uid(value):
    """Coerce an actor/user reference to a value safe for a UNIQUEIDENTIFIER
    column: a canonical GUID string when parseable, otherwise NULL.

    Audit columns (created_by / reviewed_by / closed_by / ...) are
    UNIQUEIDENTIFIER. A non-GUID string (e.g. a display name from an older UI)
    would otherwise raise a SQL conversion error and 500 the whole request. This
    keeps such a value from ever reaching the driver."""
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def rows_to_dicts(cursor):
    """Map a pyodbc cursor's current result set to a list of dicts."""
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def stringify(row):
    """Normalise identifier/user columns (``*_id`` / ``*_by``) to str so GUIDs
    serialise cleanly. All other values pass through unchanged."""
    out = {}
    for key, value in row.items():
        if (key.endswith("_id") or key.endswith("_by")) and value is not None:
            out[key] = str(value)
        else:
            out[key] = value
    return out
