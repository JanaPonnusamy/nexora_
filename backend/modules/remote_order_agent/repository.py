"""Data access for the Remote Order Agent contract.

Connections are borrowed from ``modules.nmv_integration.repository`` (``_platform``
= NEXORA_PLATFORM, ``_central`` = OrderNMC) so there is one connection policy and
the existing offline test fakes apply here too. This module adds only the
agent-contract-specific tables: the device registry (platform) and the
order-ack + result-dedup ledgers (central).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock

from modules.nmv_integration import repository as nmv_repo

_SQL_DIR = Path(__file__).with_name("sql")

_device_schema_lock = Lock()
_device_schema_ready = False
_order_schema_lock = Lock()
_order_schema_ready = False


def _apply_script(conn, filename):
    cur = conn.cursor()
    script = (_SQL_DIR / filename).read_text(encoding="utf-8")
    for batch in (part.strip() for part in script.split("\nGO")):
        if batch:
            cur.execute(batch)
    conn.commit()


def ensure_device_schema():
    global _device_schema_ready
    if _device_schema_ready:
        return
    with _device_schema_lock:
        if _device_schema_ready:
            return
        conn = nmv_repo._platform()
        try:
            _apply_script(conn, "0001_nmv_agent_device.sql")
            _device_schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def ensure_order_schema():
    global _order_schema_ready
    if _order_schema_ready:
        return
    with _order_schema_lock:
        if _order_schema_ready:
            return
        conn = nmv_repo._central()
        try:
            _apply_script(conn, "0002_nmv_agent_order.sql")
            _order_schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---- device registry (platform) ------------------------------------------

def create_device(store, token_hash, machine_name=None, agent_version=None):
    """Insert a fresh device row, revoking any prior active device for the same
    store + machine so a re-enroll supersedes the old credentials. Returns the
    new device_id (GUID str)."""
    conn = nmv_repo._platform()
    try:
        cur = conn.cursor()
        if machine_name:
            cur.execute(
                "UPDATE dbo.nmv_agent_device SET status = 'revoked' "
                "WHERE store_id = ? AND status = 'active' AND machine_name = ?",
                store["store_id"], machine_name,
            )
        device_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO dbo.nmv_agent_device "
            "(device_id, store_id, store_code, token_hash, machine_name, agent_version) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            device_id, store["store_id"], store["store_code"], token_hash,
            machine_name, agent_version,
        )
        conn.commit()
        return device_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_device_by_token_hash(token_hash):
    conn = nmv_repo._platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT device_id, store_id, store_code, status, machine_name, agent_version "
            "FROM dbo.nmv_agent_device WHERE token_hash = ?",
            token_hash,
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "device_id": str(row[0]),
            "store_id": str(row[1]),
            "store_code": row[2],
            "status": row[3],
            "machine_name": row[4],
            "agent_version": row[5],
        }
    finally:
        conn.close()


def touch_device(device_id, heartbeat=None, agent_version=None):
    conn = nmv_repo._platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.nmv_agent_device SET last_seen_at = SYSUTCDATETIME(), "
            "last_heartbeat = COALESCE(?, last_heartbeat), "
            "agent_version = COALESCE(?, agent_version) WHERE device_id = ?",
            (json.dumps(heartbeat) if heartbeat is not None else None),
            agent_version, device_id,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- order acks (central; use the caller's cursor to share a transaction) --

def get_order_ack(cur, store_name, order_id, version):
    cur.execute(
        "SELECT state, payload_sha256, applied_line_count FROM dbo.nmv_order_ack "
        "WHERE store_name = ? AND order_id = ? AND version = ?",
        store_name, order_id, version,
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"state": row[0], "payload_sha256": row[1], "applied_line_count": row[2]}


def set_order_ack(cur, store_name, order_id, version, state, payload_sha256=None,
                  applied_line_count=None, reason_code=None, reason=None):
    cur.execute(
        """
        MERGE dbo.nmv_order_ack AS target
        USING (SELECT ? AS store_name, ? AS order_id, ? AS version) AS src
          ON target.store_name = src.store_name AND target.order_id = src.order_id
             AND target.version = src.version
        WHEN MATCHED THEN UPDATE SET state = ?, payload_sha256 = ?,
            applied_line_count = ?, reason_code = ?, reason = ?, acked_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT
            (store_name, order_id, version, state, payload_sha256, applied_line_count, reason_code, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        store_name, order_id, version,
        state, payload_sha256, applied_line_count, reason_code, reason,
        store_name, order_id, version, state, payload_sha256, applied_line_count,
        reason_code, reason,
    )


# ---- result dedup ledger (central) ----------------------------------------

def result_already_applied(cur, store_id, queue_epoch, change_id):
    cur.execute(
        "SELECT 1 FROM dbo.nmv_agent_result_ledger "
        "WHERE store_id = ? AND queue_epoch = ? AND change_id = ?",
        store_id, queue_epoch, change_id,
    )
    return cur.fetchone() is not None


def record_result(cur, store_id, queue_epoch, change_id, operation, order_id, product_code):
    cur.execute(
        "INSERT INTO dbo.nmv_agent_result_ledger "
        "(store_id, queue_epoch, change_id, operation, order_id, product_code) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        store_id, queue_epoch, change_id, operation, order_id,
        (str(product_code) if product_code is not None else None),
    )


# ---- order header read (central) ------------------------------------------

def read_order_header(cur, store_name, order_id):
    cur.execute(
        "SELECT StoreName, OrderId, OrderNo, OrderDateTime, LastSaleBillNo, "
        "LastBillDateTime, LastGRN, MinDays, MaxDays "
        "FROM OrderHeaderDetails WHERE StoreName = ? AND OrderId = ?",
        store_name, order_id,
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "store_name": row[0], "order_id": row[1], "order_no": row[2],
        "order_datetime": row[3], "last_sale_bill_no": row[4],
        "last_bill_datetime": row[5], "last_grn": row[6],
        "min_days": row[7], "max_days": row[8],
    }


def delete_order_line(cur, store_name, order_id, product_code):
    cur.execute(
        "DELETE FROM OrderManagement WHERE StoreName = ? AND OrderId = ? AND ProductCode = ?",
        store_name, order_id, product_code,
    )
    return cur.rowcount or 0
