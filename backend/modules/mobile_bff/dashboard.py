from __future__ import annotations

"""Dashboard aggregate.

One call replaces the several the phone would otherwise make on every app open.
Each section is independently guarded: a module whose tables have not been
created yet (they are provisioned lazily by per-module ensure_schema calls)
returns None rather than failing the whole dashboard.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config.database import get_connection

log = logging.getLogger(__name__)

# A store agent is considered online if it checked in within this window. Matches
# the 90s threshold SyncAdminRepository.control_center() uses, so the mobile
# dashboard and the web console never disagree about who is online.
_HEARTBEAT_ONLINE_SECONDS = 90


def _section(name: str, fn, *args) -> Optional[Dict[str, Any]]:
    """Runs one section, swallowing failures so a missing table or a permission
    error degrades that card instead of blanking the screen."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - deliberate per-section isolation
        log.warning("mobile dashboard section %r unavailable: %s", name, exc)
        return None


def _store_section(store_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT store_code, store_name, is_active, last_sync_time,
                   last_sync_status, connection_status, last_heartbeat,
                   agent_version
              FROM dbo.stores
             WHERE store_id = ?
            """,
            store_id,
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    last_heartbeat = row[6]
    online = False
    if last_heartbeat is not None:
        age = (datetime.utcnow() - last_heartbeat).total_seconds()
        online = age <= _HEARTBEAT_ONLINE_SECONDS

    return {
        "store_id": store_id,
        "store_code": row[0],
        "store_name": row[1],
        "is_active": bool(row[2]),
        "last_sync_time": row[3].isoformat() if row[3] else None,
        "last_sync_status": row[4],
        "connection_status": row[5],
        "agent_online": online,
        "agent_version": row[7],
    }


def _sync_section(tenant_id: Optional[str], store_id: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Tenant-scoped on purpose. The web console's /api/sync/control-center
        # has no tenant filter, so any token can see every store platform-wide;
        # the mobile surface must not inherit that.
        if tenant_id:
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN last_heartbeat IS NOT NULL
                              AND DATEDIFF(SECOND, last_heartbeat, SYSUTCDATETIME()) <= ?
                             THEN 1 ELSE 0 END) AS online,
                    COUNT(*) AS total
                  FROM dbo.stores
                 WHERE is_active = 1 AND tenant_id = ?
                """,
                _HEARTBEAT_ONLINE_SECONDS,
                tenant_id,
            )
        else:
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN last_heartbeat IS NOT NULL
                              AND DATEDIFF(SECOND, last_heartbeat, SYSUTCDATETIME()) <= ?
                             THEN 1 ELSE 0 END) AS online,
                    COUNT(*) AS total
                  FROM dbo.stores
                 WHERE is_active = 1
                """,
                _HEARTBEAT_ONLINE_SECONDS,
            )
        row = cur.fetchone()

        cur.execute(
            """
            SELECT COUNT(*)
              FROM dbo.sync_execution
             WHERE execution_status IN ('RUNNING', 'PAUSED')
               AND store_id = ?
            """,
            store_id,
        )
        running = cur.fetchone()
    finally:
        conn.close()

    online = int(row[0] or 0) if row else 0
    total = int(row[1] or 0) if row else 0
    return {
        "stores_online": online,
        "stores_total": total,
        "stores_offline": max(total - online, 0),
        "running_for_store": int(running[0] or 0) if running else 0,
    }


def _documents_section(store_id: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'REVIEW_PENDING' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status IN ('UPLOADED', 'OCR_RUNNING', 'EXTRACTED')
                         THEN 1 ELSE 0 END)
              FROM dbo.doc_import
             WHERE store_id = ?
            """,
            store_id,
        )
        row = cur.fetchone()
    finally:
        conn.close()

    return {
        "awaiting_review": int(row[0] or 0) if row else 0,
        "failed": int(row[1] or 0) if row else 0,
        "processing": int(row[2] or 0) if row else 0,
    }


def _procurement_section(store_id: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 cycle_id, cycle_no, status, active_refresh_id
              FROM procurement.procurement_cycles
             WHERE store_id = ? AND is_deleted = 0 AND status = 'OPEN'
             ORDER BY cycle_no DESC
            """,
            store_id,
        )
        cycle = cur.fetchone()

        pending = 0
        if cycle and cycle[3]:
            cur.execute(
                """
                SELECT COUNT(*)
                  FROM procurement.procurement_order_items
                 WHERE refresh_id = ? AND item_status = 'PENDING_REVIEW'
                """,
                cycle[3],
            )
            found = cur.fetchone()
            pending = int(found[0] or 0) if found else 0
    finally:
        conn.close()

    if not cycle:
        return {"active_cycle": None, "pending_review": 0}

    return {
        "active_cycle": {
            "cycle_id": str(cycle[0]),
            "cycle_no": cycle[1],
            "status": cycle[2],
            "active_refresh_id": str(cycle[3]) if cycle[3] else None,
        },
        "pending_review": pending,
    }


def build(user: Dict[str, Any], store_id: Optional[str]) -> Dict[str, Any]:
    """Assembles the dashboard payload for one user in one store context."""
    tenant_id = user.get("tenant_id")

    payload: Dict[str, Any] = {
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "first_name": user.get("first_name"),
            "is_platform_user": user.get("is_platform_user", False),
            "tenant_id": tenant_id,
            "module_count": len(user.get("modules") or []),
        },
        "store": None,
        "sync": None,
        "documents": None,
        "procurement": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if store_id:
        payload["store"] = _section("store", _store_section, store_id)
        payload["sync"] = _section("sync", _sync_section, tenant_id, store_id)
        payload["documents"] = _section("documents", _documents_section, store_id)
        payload["procurement"] = _section("procurement", _procurement_section, store_id)

    return payload
