"""Data access for the NMV integration boundary.

Everything the agent reads or writes lives in the OrderNMC (legacy) database and
is hard-scoped to a single StoreName. The additive control tables
(nmv_sync_watermark / nmv_sync_message / nmv_sync_audit) live there too so an
inbound write and its idempotency record commit in one transaction.

Store *identity* is resolved against NEXORA_PLATFORM.dbo.stores (where device
assignments point); the OrderNMC StoreName equals the platform store_code
(the short code, e.g. 'NMV' -- same convention the Legacy Order module uses).

Connections go through the thin `_central()` / `_platform()` wrappers so tests
can substitute a fake.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock

from config.database import get_connection as _get_platform_connection
from modules.legacy_order import database as legacy_db

_SCHEMA_FILE = Path(__file__).with_name("sql") / "0001_nmv_integration.sql"
_schema_lock = Lock()
_schema_ready = False

_ENROLL_SCHEMA_FILE = Path(__file__).with_name("sql") / "0002_nmv_enrollment_code.sql"
_enroll_schema_lock = Lock()
_enroll_schema_ready = False


def _central():
    """Open an OrderNMC connection (with the Legacy module's auto-recovery)."""
    return legacy_db.get_central_connection()


def _platform():
    """Open a NEXORA_PLATFORM connection (for store identity resolution)."""
    return _get_platform_connection()


# ---- schema ---------------------------------------------------------------

def ensure_schema():
    """Apply the idempotent NMV integration DDL once per backend process."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn = _central()
        try:
            cur = conn.cursor()
            script = _SCHEMA_FILE.read_text(encoding="utf-8")
            for batch in (part.strip() for part in script.split("\nGO")):
                if batch:
                    cur.execute(batch)
            conn.commit()
            _schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---- store identity (platform) -------------------------------------------

def resolve_platform_store(store_code):
    """Resolve a store_code to its platform identity, or None if unknown.

    The OrderNMC StoreName used for all data scoping is the store_code itself.
    """
    if not store_code or not str(store_code).strip():
        return None
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT store_id, tenant_id, store_code, store_name, is_active "
            "FROM dbo.stores WHERE store_code = ?",
            str(store_code).strip(),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "store_id": str(row[0]),
            "tenant_id": str(row[1]) if row[1] else None,
            "store_code": row[2],
            "store_name": row[3],
            "is_active": bool(row[4]) if row[4] is not None else True,
            "order_store_name": row[2],  # OrderNMC StoreName == short code
        }
    finally:
        conn.close()


# ---- enrollment codes (platform) -----------------------------------------
#
# A one-time code that lets an NMV device self-register (reusing the existing
# device-identity module) without a store-user login. The plaintext code is
# never stored; only its SHA-256 hash is. Lives in the platform DB next to
# device_registrations so claim + register touch one database.

def ensure_enrollment_schema():
    """Apply the idempotent enrollment-code DDL once per backend process."""
    global _enroll_schema_ready
    if _enroll_schema_ready:
        return
    with _enroll_schema_lock:
        if _enroll_schema_ready:
            return
        conn = _platform()
        try:
            cur = conn.cursor()
            script = _ENROLL_SCHEMA_FILE.read_text(encoding="utf-8")
            for batch in (part.strip() for part in script.split("\nGO")):
                if batch:
                    cur.execute(batch)
            conn.commit()
            _enroll_schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _uid(value):
    """Treat empty / non-GUID placeholders as NULL so a uniqueidentifier cast
    can't blow up on a blank or malformed value."""
    if value in (None, "", "None"):
        return None
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
    return str(value)


def create_enrollment_code(store_id, store_code, code_hash, ttl_seconds,
                           created_by=None, created_by_username=None):
    """Supersede any still-active code for the store, then insert a new one.

    Returns (code_id, expires_at_iso). Only the hash is persisted; the caller
    holds the single plaintext copy to hand back to the admin once.
    """
    conn = _platform()
    try:
        cur = conn.cursor()
        # At most one active code per store: a freshly generated code
        # immediately invalidates any earlier unused one.
        cur.execute(
            "UPDATE dbo.nmv_enrollment_code SET status = 'superseded' "
            "WHERE store_id = ? AND status = 'active'",
            store_id,
        )
        cur.execute(
            """
            INSERT INTO dbo.nmv_enrollment_code
                (id, store_id, store_code, code_hash, expires_at, created_by, created_by_username)
            OUTPUT INSERTED.id, INSERTED.expires_at
            VALUES (NEWID(), ?, ?, ?, DATEADD(SECOND, ?, SYSUTCDATETIME()), ?, ?)
            """,
            store_id, store_code, code_hash, int(ttl_seconds),
            _uid(created_by), created_by_username,
        )
        row = cur.fetchone()
        conn.commit()
        return str(row[0]), (row[1].isoformat() if row[1] else None)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def redeem_enrollment_code(code_hash, store_id, max_attempts):
    """Look a code up by hash and atomically consume it if it is usable.

    All state transitions happen in one connection so single-use is race-safe:
    the claim is a conditional UPDATE guarded by both status='active' and a
    live expiry, and only the one caller whose UPDATE affects a row wins.

    Returns a dict {"status": <outcome>, "code": {...} | None} where outcome is
    one of: not_found, wrong_store, locked, used, superseded, expired,
    consumed, ok. Never returns or logs the plaintext code.
    """
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, store_id, store_code, status, expires_at, used_at, "
            "attempt_count, created_by, created_by_username "
            "FROM dbo.nmv_enrollment_code WHERE code_hash = ?",
            code_hash,
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return {"status": "not_found", "code": None}

        code = {
            "id": str(row[0]),
            "store_id": str(row[1]),
            "store_code": row[2],
            "status": row[3],
            "attempt_count": int(row[6] or 0),
            "created_by": str(row[7]) if row[7] else None,
            "created_by_username": row[8],
        }

        # Record the presentation (brute-force signal + audit), always.
        cur.execute(
            "UPDATE dbo.nmv_enrollment_code SET attempt_count = attempt_count + 1 WHERE id = ?",
            code["id"],
        )
        new_attempts = code["attempt_count"] + 1

        # The code is bound to one store: a code issued for NMV can never enroll
        # any other store, regardless of the store_code the client sends.
        if code["store_id"] != str(store_id):
            conn.commit()
            return {"status": "wrong_store", "code": code}

        if code["status"] == "active" and new_attempts > max_attempts:
            cur.execute(
                "UPDATE dbo.nmv_enrollment_code SET status = 'locked' WHERE id = ? AND status = 'active'",
                code["id"],
            )
            conn.commit()
            return {"status": "locked", "code": code}

        if code["status"] != "active":
            conn.commit()
            return {"status": code["status"], "code": code}  # used | superseded | locked

        # Atomic single-use + expiry claim.
        cur.execute(
            "UPDATE dbo.nmv_enrollment_code SET status = 'used', used_at = SYSUTCDATETIME() "
            "WHERE id = ? AND status = 'active' AND expires_at > SYSUTCDATETIME()",
            code["id"],
        )
        if cur.rowcount and cur.rowcount == 1:
            conn.commit()
            return {"status": "ok", "code": code}

        # Claim missed: either expired (still 'active' but past expiry) or a
        # concurrent enroll consumed it first.
        cur.execute("SELECT status FROM dbo.nmv_enrollment_code WHERE id = ?", code["id"])
        after = cur.fetchone()
        conn.commit()
        if after and after[0] == "active":
            return {"status": "expired", "code": code}
        return {"status": "consumed", "code": code}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def attach_device_to_code(code_id, device_id):
    """Record which device consumed a code (audit linkage; the code is already
    marked 'used' by redeem_enrollment_code)."""
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.nmv_enrollment_code SET device_id = ? WHERE id = ?",
            _uid(device_id), code_id,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- watermarks -----------------------------------------------------------

def get_watermark(cur, store_name, entity):
    cur.execute(
        "SELECT strategy, watermark_num, watermark_str FROM dbo.nmv_sync_watermark "
        "WHERE store_name = ? AND entity = ?",
        store_name, entity,
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"strategy": row[0], "watermark_num": row[1], "watermark_str": row[2]}


def set_watermark(cur, store_name, entity, strategy, watermark_num=None, watermark_str=None):
    cur.execute(
        """
        MERGE dbo.nmv_sync_watermark AS target
        USING (SELECT ? AS store_name, ? AS entity) AS src
          ON target.store_name = src.store_name AND target.entity = src.entity
        WHEN MATCHED THEN UPDATE SET strategy = ?, watermark_num = ?,
            watermark_str = ?, updated_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (store_name, entity, strategy, watermark_num, watermark_str)
            VALUES (?, ?, ?, ?, ?);
        """,
        store_name, entity,
        strategy, watermark_num, watermark_str,
        store_name, entity, strategy, watermark_num, watermark_str,
    )


def list_watermarks(store_name):
    conn = _central()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT entity, strategy, watermark_num, watermark_str "
            "FROM dbo.nmv_sync_watermark WHERE store_name = ? ORDER BY entity",
            store_name,
        )
        out = []
        for r in cur.fetchall():
            out.append({
                "entity": r[0],
                "strategy": r[1],
                "watermark": r[2] if r[2] is not None else r[3],
            })
        return out
    finally:
        conn.close()


# ---- idempotency ledger ---------------------------------------------------

def load_message(cur, message_id):
    cur.execute(
        "SELECT message_id, store_name, direction, kind, status, rows_in, "
        "rows_applied, error, response_json FROM dbo.nmv_sync_message WHERE message_id = ?",
        message_id,
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "message_id": str(row[0]),
        "store_name": row[1],
        "direction": row[2],
        "kind": row[3],
        "status": row[4],
        "rows_in": row[5],
        "rows_applied": row[6],
        "error": row[7],
        "response_json": row[8],
    }


def insert_message(cur, message_id, store_name, direction, kind, rows_in):
    """Insert a 'processing' ledger row. Raises on PK violation (= duplicate)."""
    cur.execute(
        "INSERT INTO dbo.nmv_sync_message (message_id, store_name, direction, kind, status, rows_in) "
        "VALUES (?, ?, ?, ?, 'processing', ?)",
        message_id, store_name, direction, kind, rows_in,
    )


def complete_message(cur, message_id, status, rows_applied, response, error=None):
    cur.execute(
        "UPDATE dbo.nmv_sync_message SET status = ?, rows_applied = ?, "
        "response_json = ?, error = ? WHERE message_id = ?",
        status, rows_applied,
        json.dumps(response) if response is not None else None,
        (error[:1000] if error else None),
        message_id,
    )


# ---- audit ----------------------------------------------------------------

def insert_audit(cur, store_name, device_id, message_id, entity, direction,
                 rows, status="ok", detail=None):
    cur.execute(
        "INSERT INTO dbo.nmv_sync_audit (store_name, device_id, message_id, entity, "
        "direction, rows, ended_at, status, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), ?, ?)",
        store_name, (device_id or None), message_id, entity, direction, rows,
        status, (detail[:1000] if detail else None),
    )


def recent_audit(store_name, limit=20):
    limit = max(1, min(int(limit), 100))
    conn = _central()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT TOP {limit} entity, direction, rows, started_at, status, detail "
            "FROM dbo.nmv_sync_audit WHERE store_name = ? ORDER BY started_at DESC, audit_id DESC",
            store_name,
        )
        out = []
        for r in cur.fetchall():
            out.append({
                "entity": r[0], "direction": r[1], "rows": r[2],
                "at": r[3].isoformat() if r[3] else None,
                "status": r[4], "detail": r[5],
            })
        return out
    finally:
        conn.close()


# ---- destination introspection (uplink staging) --------------------------

def dest_column_types(cur, dest_table, columns):
    """INFORMATION_SCHEMA data type for each requested dest column (lower-cased).

    Used to build a staging table that matches the real column types so values
    round-trip faithfully through the MERGE rather than relying on NVARCHAR
    implicit conversion.
    """
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
        dest_table,
    )
    by_name = {}
    for r in cur.fetchall():
        by_name[str(r[0]).lower()] = {
            "data_type": str(r[1]).lower(),
            "char_len": r[2],
            "precision": r[3],
            "scale": r[4],
        }
    return {c: by_name.get(c.lower()) for c in columns}


# ---- order-result apply ---------------------------------------------------

_RESULT_COLUMN_SQL = {
    "order_qty": "OrderQty",
    "or_qty": "OrQty",
    "qty_check": "QtyCheck",
    "remarks": "Remarks",
    "or_supplier": "OrSupplier",
    "or_supplier_code": "OrSupplierCode",
    "status": "Status",
}


def apply_order_result(cur, store_name, order_id, item: dict):
    """Apply one processed-order line to OrderManagement.

    Scoped to (StoreName, OrderId, ProductCode) and limited to the whitelisted
    result columns. Returns 'applied' | 'conflict' | 'missing'.
    """
    product_code = item.get("product_code")
    if product_code is None:
        return "missing"

    # Only the fields actually supplied are written; expected_status is a guard,
    # never a written column.
    set_parts, params = [], []
    for key, col in _RESULT_COLUMN_SQL.items():
        if key in item and item[key] is not None:
            set_parts.append(f"[{col}] = ?")
            params.append(item[key])
    if not set_parts:
        return "missing"

    where = "StoreName = ? AND OrderId = ? AND ProductCode = ?"
    where_params = [store_name, order_id, product_code]

    expected = item.get("expected_status")
    if expected is not None:
        where += " AND Status = ?"
        where_params.append(expected)

    cur.execute(
        f"UPDATE OrderManagement SET {', '.join(set_parts)} WHERE {where}",
        *params, *where_params,
    )
    if cur.rowcount and cur.rowcount > 0:
        return "applied"

    # Nothing updated: distinguish a genuine conflict (row exists but Status
    # moved) from a missing row, so the agent can act differently.
    if expected is not None:
        cur.execute(
            "SELECT COUNT(1) FROM OrderManagement "
            "WHERE StoreName = ? AND OrderId = ? AND ProductCode = ?",
            store_name, order_id, product_code,
        )
        row = cur.fetchone()
        if row and row[0]:
            return "conflict"
    return "missing"


# ---- downlink reads -------------------------------------------------------

def current_order_id(cur, store_name):
    cur.execute(
        "SELECT MAX(OrderId) FROM OrderManagement WHERE StoreName = ?", store_name
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None
