"""Order cache monitor: per-store health snapshot (file age, last write-back
time/status, unsynced row count, connection state) plus the admin WhatsApp
alert fired when a pending write-back blocks the next Order Process run.

Design doc: Order_Sync_Redesign_Plan.md section 3.3, extended per owner
instruction (this turn): Order Process must now refuse to build a fresh
cache for a store while that store's existing cache still has pending
write-back that failed to drain -- the full prior order's record must
always make it back to HO before the next one overwrites it. On that
refusal, an admin alert goes out (reusing the same WhatsApp-profile
convention as modules.sync.health_monitor, not a second notification path).
"""
import logging
import os
import sqlite3
from datetime import datetime

from . import builder

logger = logging.getLogger(__name__)

_CONNECTION_STATUS_KEY = "connection_status"  # 'ok' | 'broken' (cache_meta)


def _file_age_seconds(path):
    try:
        return (datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))).total_seconds()
    except OSError:
        return None


def _read_one(store_name):
    path = builder.cache_path(store_name)
    if not os.path.exists(path):
        return {
            "store_name": store_name,
            "exists": False,
            "cache_path": path,
        }

    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        meta = {row["key"]: row["value"] for row in cur.execute("SELECT key, value FROM cache_meta")}
        pending_count = cur.execute("SELECT COUNT(*) FROM pending_writeback").fetchone()[0]
        unsynced_count = cur.execute(
            "SELECT COUNT(*) FROM order_lines WHERE updated_at IS NOT NULL "
            "AND (synced_at IS NULL OR synced_at < updated_at)"
        ).fetchone()[0]
        row_count = cur.execute("SELECT COUNT(*) FROM order_lines").fetchone()[0]
        mtime = os.path.getmtime(path)
        return {
            "store_name": store_name,
            "exists": True,
            "cache_path": path,
            "file_created_at": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
            "file_age_seconds": int(_file_age_seconds(path) or 0),
            "built_at": meta.get("built_at"),
            "schema_version": meta.get("schema_version"),
            "row_count": row_count,
            "pending_writeback_count": pending_count,
            "unsynced_row_count": unsynced_count,
            "last_writeback_at": meta.get("last_writeback_at"),
            "last_writeback_status": meta.get("last_writeback_status"),
            "last_writeback_error": meta.get("last_writeback_error") or None,
            "connection_status": meta.get(_CONNECTION_STATUS_KEY, "ok" if pending_count == 0 else "broken"),
        }
    finally:
        conn.close()


def status_for_store(store_name):
    return _read_one(store_name)


def status_all(store_names):
    """One row per store (list). Stores with no cache file yet still appear
    (exists: false) so the monitor shows the whole fleet, not just the ones
    that happen to have been processed since the feature was enabled."""
    return [_read_one(name) for name in store_names]


def mark_connection_broken(cache_file_path, error):
    """Called when a push/pull to HO could not even be attempted (no network
    path), as opposed to a drain that ran and failed server-side. Lets the
    monitor show 'broken' distinctly from 'pending rows, HO reachable'."""
    conn = sqlite3.connect(cache_file_path, timeout=10)
    try:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)",
            (_CONNECTION_STATUS_KEY, "broken"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('connection_broken_at', ?)",
            (now,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('connection_broken_error', ?)",
            (str(error),),
        )
        conn.commit()
    finally:
        conn.close()


def mark_connection_ok(cache_file_path):
    conn = sqlite3.connect(cache_file_path, timeout=10)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)",
            (_CONNECTION_STATUS_KEY, "ok"),
        )
        conn.commit()
    finally:
        conn.close()


def _alert_recipient():
    """Reuses modules.sync.health_monitor's own profile-resolution helper so
    there is exactly one place that decides which WhatsApp profile/phone
    admin alerts go to -- no second convention to keep in sync."""
    from modules.sync import health_monitor
    return health_monitor._alert_phone()


def send_blocked_alert(store_name, error):
    """Order Process refused to start a new order for `store_name` because
    the existing cache file's pending write-back would not drain. Sends one
    WhatsApp alert to the admin profile/phone (best-effort -- a failed send
    here must never raise, since it runs inside the request path that is
    already failing the order for the caller)."""
    try:
        profile_id, phone = _alert_recipient()
        if not profile_id or not phone:
            logger.warning(
                "order cache blocked alert not sent for %s (no WhatsApp profile/phone): %s",
                store_name, error,
            )
            return False
        from modules.whatsapp import service as wa
        lines = [
            "NEXORA ORDER CACHE BLOCKED " + datetime.now().strftime("%d/%m %H:%M"),
            f"Store: {store_name}",
            "Order Process held: the previous order's pending write-back has not reached HO.",
            f"Detail: {error}",
            "Resolve from Sync > Order Cache Monitor (force drain / force pull) before processing this store again.",
        ]
        result = wa.send_message(profile_id, phone, "\n".join(lines))
        ok = (result or {}).get("status") == "sent"
        if not ok:
            logger.warning("order cache blocked alert WhatsApp send not confirmed: %s", result)
        return ok
    except Exception:
        logger.exception("order cache blocked alert failed for %s", store_name)
        return False
