"""Idempotency / write-path replay protection.

Every inbound POST carries a client-generated message_id. The first time it is
seen HO records it (status 'processing' -> 'applied') inside the same
transaction as the data write, then commits. A replay finds a committed
'applied' row and returns its stored response without applying anything.

A committed ledger row is therefore proof the work already landed (the row and
the data commit together; a crash before commit rolls both back, so a retry
re-processes cleanly). The PK on message_id also makes two simultaneous
duplicate POSTs safe: the second INSERT fails and is treated as a replay.
"""
from __future__ import annotations

import json

from modules.nmv_integration import repository


def already_applied(cur, message_id) -> dict | None:
    """Return the stored response for an already-applied message, else None."""
    existing = repository.load_message(cur, message_id)
    if existing and existing.get("status") == "applied":
        raw = existing.get("response_json")
        try:
            return json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            return {}
    return None


def is_duplicate_insert(exc) -> bool:
    """True if the exception is a primary-key / unique violation.

    Recognises pyodbc's SQLSTATE 23000 and SQL Server error numbers 2627/2601
    without importing pyodbc (so the module imports cleanly where the driver is
    absent, e.g. in unit tests)."""
    args = getattr(exc, "args", None) or ()
    text = " ".join(str(a) for a in args) + " " + str(exc)
    return any(code in text for code in ("23000", "2627", "2601")) and (
        "duplicate" in text.lower()
        or "primary key" in text.lower()
        or "unique" in text.lower()
        or "23000" in text
    )
