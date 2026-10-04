"""Data layer for Stock Client fleet management.

Follows the module conventions in modules/agent_ops/repository.py: one idempotent
``ensure_schema`` applied once per process, raw pyodbc via ``config.database``,
``?`` params, dict rows. Every state-changing admin action also writes a
``dbo.stock_client_events`` audit row (who/what/when/result).
"""
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from config.database import get_connection

_SCHEMA_FILE = Path(__file__).with_name("sql") / "0001_stock_client_ops.sql"
_schema_lock = Lock()
_schema_ready = False

# A target is "live" (the watchdog should still act on it) until it reaches a
# terminal state. FAILED is terminal for the watchdog - only an HO retry resets
# it to PENDING, so a bad release can never trap a store in an endless loop.
_ACTIVE_TARGET_STATUSES = (
    "PENDING", "DOWNLOADING", "VERIFYING", "INSTALLING", "RESTARTING",
)
_TERMINAL_TARGET_STATUSES = ("SUCCESS", "ROLLED_BACK", "FAILED")

# Heartbeat history retention (newest N rows per installation are kept).
_HEARTBEAT_RETENTION = 500


def ensure_schema():
    """Apply the idempotent Stock Client Ops DDL once per backend process."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn = get_connection()
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


# ---- helpers --------------------------------------------------------------

def _rows_to_dicts(cursor):
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _new_guid():
    return str(uuid4()).upper()


def _next_human_id(cursor, table, column, prefix, width):
    """Generate the next zero-padded human id (e.g. REL-2026-00007). Zero-pad
    keeps string-DESC order == numeric order, so MAX(previous)+1 is a cheap
    read. A rare concurrent collision surfaces as a unique-index violation the
    caller retries, not silent reuse."""
    year = datetime.utcnow().year
    like = f"{prefix}-{year}-%"
    cursor.execute(
        f"SELECT TOP 1 {column} FROM dbo.{table} WHERE {column} LIKE ? ORDER BY {column} DESC",
        (like,),
    )
    row = cursor.fetchone()
    seq = 1
    if row and row[0]:
        try:
            seq = int(str(row[0]).rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}-{year}-{str(seq).zfill(width)}"


def _insert_event(cursor, *, event_type, actor=None, installation_id=None,
                  deployment_id=None, store_id=None, detail=None,
                  target_version=None, result=None):
    cursor.execute(
        """
        INSERT INTO dbo.stock_client_events
        (installation_id, deployment_id, store_id, event_type, actor, detail,
         target_version, result, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
        """,
        (installation_id, deployment_id, store_id, event_type, actor, detail,
         target_version, result),
    )


# ---- releases -------------------------------------------------------------

def create_release(*, version, file_name, package_path, sha256, file_size,
                   signature=None, release_notes=None, build=None,
                   min_supported_version=None, created_by=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        release_pk = _new_guid()
        release_id = _next_human_id(cur, "stock_client_releases", "release_id", "REL", 5)
        cur.execute(
            """
            INSERT INTO dbo.stock_client_releases
            (id, version, release_id, build, file_name, package_path, sha256,
             file_size, signature, release_notes, status, min_supported_version,
             created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, SYSUTCDATETIME())
            """,
            (release_pk, version, release_id, build, file_name, package_path,
             sha256, file_size, signature, release_notes, min_supported_version,
             created_by),
        )
        _insert_event(cur, event_type="RELEASE_CREATED", actor=created_by,
                      detail=f"{version} ({release_id})", target_version=version,
                      result="DRAFT")
        conn.commit()
        return get_release(release_pk)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_releases():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(id AS VARCHAR(36)) AS id, version, release_id, build,
                   file_name, sha256, file_size, status, release_notes,
                   min_supported_version, created_by, created_at,
                   approved_by, approved_at
            FROM dbo.stock_client_releases
            ORDER BY created_at DESC, version DESC
            """
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_release(release_pk):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(id AS VARCHAR(36)) AS id, version, release_id, build,
                   file_name, package_path, sha256, file_size, signature, status,
                   release_notes, min_supported_version, created_by, created_at,
                   approved_by, approved_at
            FROM dbo.stock_client_releases WHERE id = ?
            """,
            (release_pk,),
        )
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None
    finally:
        conn.close()


def get_release_by_version(version):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(id AS VARCHAR(36)) AS id, version, release_id, file_name,
                   package_path, sha256, file_size, signature, status
            FROM dbo.stock_client_releases WHERE version = ?
            """,
            (version,),
        )
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None
    finally:
        conn.close()


def set_release_status(release_pk, status, actor=None):
    """Move a release along its lifecycle (APPROVED stamps approver/time)."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        if status == "APPROVED":
            cur.execute(
                """
                UPDATE dbo.stock_client_releases
                SET status = 'APPROVED', approved_by = ?, approved_at = SYSUTCDATETIME()
                WHERE id = ?
                """,
                (actor, release_pk),
            )
        else:
            cur.execute(
                "UPDATE dbo.stock_client_releases SET status = ? WHERE id = ?",
                (status, release_pk),
            )
        updated = cur.rowcount
        if updated:
            _insert_event(cur, event_type=f"RELEASE_{status}", actor=actor,
                          detail=str(release_pk), result=status)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- deployments (rollouts) ----------------------------------------------

def create_deployment(*, release_pk, scope, store_ids, created_by=None):
    """Create a DRAFT rollout and materialize one target row per store. Targets
    start DRAFT; authorize_deployment flips them to PENDING so unauthorized
    rollouts are never visible to a watchdog even though the rows exist."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT version FROM dbo.stock_client_releases WHERE id = ?",
            (release_pk,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("release not found")
        version = row[0]

        deployment_id = _new_guid()
        rollout_id = _next_human_id(cur, "stock_client_deployments", "rollout_id", "ROLL", 4)
        cur.execute(
            """
            INSERT INTO dbo.stock_client_deployments
            (id, rollout_id, release_id, release_version, scope, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, 'DRAFT', ?, SYSUTCDATETIME())
            """,
            (deployment_id, rollout_id, release_pk, version, scope, created_by),
        )
        for store_id in store_ids:
            cur.execute(
                """
                SELECT TOP 1 CAST(installation_id AS VARCHAR(36)), client_version
                FROM dbo.stock_client_installations
                WHERE store_id = ? ORDER BY last_heartbeat_at DESC
                """,
                (store_id,),
            )
            inst = cur.fetchone()
            installation_id = inst[0] if inst else None
            current_version = inst[1] if inst else None
            cur.execute(
                """
                INSERT INTO dbo.stock_client_deployment_targets
                (id, deployment_id, store_id, installation_id, current_version,
                 target_version, status, progress, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', 0, SYSUTCDATETIME())
                """,
                (_new_guid(), deployment_id, store_id, installation_id,
                 current_version, version),
            )
        _insert_event(cur, event_type="DEPLOYMENT_CREATED", actor=created_by,
                      deployment_id=deployment_id,
                      detail=f"{rollout_id} scope={scope} stores={len(store_ids)}",
                      target_version=version, result="DRAFT")
        conn.commit()
        return get_deployment(deployment_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def authorize_deployment(deployment_id, actor=None):
    """The explicit AUTHORIZE gate: DRAFT -> PENDING on the rollout and all its
    targets. Only now do watchdogs see work to do (see get_installation_state).
    Also marks the release ROLLED_OUT."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, release_id FROM dbo.stock_client_deployments WHERE id = ?",
            (deployment_id,),
        )
        row = cur.fetchone()
        if not row:
            return 0
        if row[0] != "DRAFT":
            return -1  # already authorized/cancelled - caller maps to 409
        release_pk = str(row[1])
        cur.execute(
            """
            UPDATE dbo.stock_client_deployments
            SET status = 'PENDING', authorized_by = ?, authorized_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (actor, deployment_id),
        )
        cur.execute(
            """
            UPDATE dbo.stock_client_deployment_targets
            SET status = 'PENDING', updated_at = SYSUTCDATETIME()
            WHERE deployment_id = ? AND status = 'DRAFT'
            """,
            (deployment_id,),
        )
        cur.execute(
            "UPDATE dbo.stock_client_releases SET status = 'ROLLED_OUT' WHERE id = ? AND status = 'APPROVED'",
            (release_pk,),
        )
        _insert_event(cur, event_type="DEPLOYMENT_AUTHORIZED", actor=actor,
                      deployment_id=deployment_id, result="PENDING")
        conn.commit()
        return 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cancel_deployment(deployment_id, actor=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.stock_client_deployments SET status = 'CANCELLED' WHERE id = ? AND status IN ('DRAFT','PENDING','IN_PROGRESS')",
            (deployment_id,),
        )
        updated = cur.rowcount
        if updated:
            cur.execute(
                """
                UPDATE dbo.stock_client_deployment_targets
                SET status = 'FAILED', error = 'deployment cancelled', updated_at = SYSUTCDATETIME()
                WHERE deployment_id = ? AND status IN ('DRAFT','PENDING')
                """,
                (deployment_id,),
            )
            _insert_event(cur, event_type="DEPLOYMENT_CANCELLED", actor=actor,
                          deployment_id=deployment_id, result="CANCELLED")
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retry_target(deployment_id, target_id, actor=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.stock_client_deployment_targets
            SET status = 'PENDING', progress = 0, error = NULL,
                started_at = NULL, completed_at = NULL, updated_at = SYSUTCDATETIME()
            WHERE id = ? AND deployment_id = ?
            """,
            (target_id, deployment_id),
        )
        updated = cur.rowcount
        if updated:
            # Re-open the rollout if it had settled, so the retried store is served.
            cur.execute(
                "UPDATE dbo.stock_client_deployments SET status = 'PENDING', completed_at = NULL WHERE id = ? AND status IN ('COMPLETED','IN_PROGRESS')",
                (deployment_id,),
            )
            _insert_event(cur, event_type="TARGET_RETRY", actor=actor,
                          deployment_id=deployment_id, result="PENDING")
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_deployments():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(d.id AS VARCHAR(36)) AS id, d.rollout_id, d.release_version,
                   d.scope, d.status, d.created_by, d.created_at,
                   d.authorized_by, d.authorized_at, d.completed_at,
                   COUNT(t.id) AS target_count,
                   SUM(CASE WHEN t.status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
                   SUM(CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END) AS failed_count
            FROM dbo.stock_client_deployments d
            LEFT JOIN dbo.stock_client_deployment_targets t ON t.deployment_id = d.id
            GROUP BY d.id, d.rollout_id, d.release_version, d.scope, d.status,
                     d.created_by, d.created_at, d.authorized_by, d.authorized_at, d.completed_at
            ORDER BY d.created_at DESC
            """
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_deployment(deployment_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(id AS VARCHAR(36)) AS id, rollout_id,
                   CAST(release_id AS VARCHAR(36)) AS release_id, release_version,
                   scope, status, created_by, created_at, authorized_by,
                   authorized_at, completed_at
            FROM dbo.stock_client_deployments WHERE id = ?
            """,
            (deployment_id,),
        )
        rows = _rows_to_dicts(cur)
        if not rows:
            return None
        deployment = rows[0]
        cur.execute(
            """
            SELECT CAST(t.id AS VARCHAR(36)) AS id, CAST(t.store_id AS VARCHAR(36)) AS store_id,
                   st.store_code, st.store_name,
                   CAST(t.installation_id AS VARCHAR(36)) AS installation_id,
                   t.current_version, t.target_version, t.status, t.progress,
                   t.error, t.started_at, t.completed_at, t.updated_at
            FROM dbo.stock_client_deployment_targets t
            LEFT JOIN dbo.stores st ON st.store_id = t.store_id
            WHERE t.deployment_id = ?
            ORDER BY st.store_code
            """,
            (deployment_id,),
        )
        deployment["targets"] = _rows_to_dicts(cur)
        return deployment
    finally:
        conn.close()


# ---- installations + heartbeat -------------------------------------------

def register_installation(*, installation_id, device_id=None, tenant_id=None,
                          store_id=None, fingerprint_hash=None, hostname=None,
                          os_version=None, client_version=None):
    """Upsert the installation registry row. If a known installation reports a
    different fingerprint, flag DEVICE_CHANGED instead of silently re-binding
    (spec section 8) - HO decides what to do."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT fingerprint_hash FROM dbo.stock_client_installations WHERE installation_id = ?",
            (installation_id,),
        )
        existing = cur.fetchone()
        if existing is None:
            cur.execute(
                """
                INSERT INTO dbo.stock_client_installations
                (installation_id, device_id, tenant_id, store_id, fingerprint_hash,
                 hostname, os_version, client_version, status, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', SYSUTCDATETIME())
                """,
                (installation_id, device_id, tenant_id, store_id, fingerprint_hash,
                 hostname, os_version, client_version),
            )
            _insert_event(cur, event_type="INSTALLATION_REGISTERED",
                          installation_id=installation_id, store_id=store_id,
                          detail=hostname, result="ACTIVE")
        else:
            changed = (
                fingerprint_hash and existing[0] and fingerprint_hash != existing[0]
            )
            cur.execute(
                """
                UPDATE dbo.stock_client_installations
                SET device_id = COALESCE(?, device_id),
                    tenant_id = COALESCE(?, tenant_id),
                    store_id = COALESCE(?, store_id),
                    hostname = COALESCE(?, hostname),
                    os_version = COALESCE(?, os_version),
                    client_version = COALESCE(?, client_version),
                    status = CASE WHEN ? = 1 THEN 'DEVICE_CHANGED' ELSE status END
                WHERE installation_id = ?
                """,
                (device_id, tenant_id, store_id, hostname, os_version,
                 client_version, 1 if changed else 0, installation_id),
            )
            if changed:
                _insert_event(cur, event_type="DEVICE_CHANGED",
                              installation_id=installation_id, store_id=store_id,
                              detail="fingerprint mismatch", result="DEVICE_CHANGED")
        conn.commit()
        return get_installation(installation_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_heartbeat(*, installation_id, observed_ip=None, watchdog_version=None,
                     watchdog_status=None, client_status=None, client_version=None,
                     local_ip=None, os_version=None, last_update_status=None,
                     last_error=None, target_version=None, target_status=None,
                     target_progress=None, target_error=None):
    """Upsert live status, append a bounded history row, and (if the watchdog
    reported update progress) advance the matching deployment target."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.stock_client_installations
            SET observed_ip = COALESCE(?, observed_ip),
                watchdog_version = COALESCE(?, watchdog_version),
                watchdog_status = COALESCE(?, watchdog_status),
                client_status = COALESCE(?, client_status),
                client_version = COALESCE(?, client_version),
                local_ip = COALESCE(?, local_ip),
                os_version = COALESCE(?, os_version),
                last_update_status = COALESCE(?, last_update_status),
                last_error = ?,
                last_heartbeat_at = SYSUTCDATETIME()
            WHERE installation_id = ?
            """,
            (observed_ip, watchdog_version, watchdog_status, client_status,
             client_version, local_ip, os_version, last_update_status,
             last_error, installation_id),
        )
        if cur.rowcount == 0:
            # Heartbeat before an explicit register (e.g. watchdog came up
            # first): create a minimal ACTIVE row so nothing is dropped.
            cur.execute(
                """
                INSERT INTO dbo.stock_client_installations
                (installation_id, observed_ip, watchdog_version, watchdog_status,
                 client_status, client_version, local_ip, os_version,
                 last_update_status, last_error, last_heartbeat_at, status, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), 'ACTIVE', SYSUTCDATETIME())
                """,
                (installation_id, observed_ip, watchdog_version, watchdog_status,
                 client_status, client_version, local_ip, os_version,
                 last_update_status, last_error),
            )
        cur.execute(
            """
            INSERT INTO dbo.stock_client_heartbeats
            (installation_id, client_version, watchdog_version, client_status,
             watchdog_status, last_update_status, local_ip, observed_ip, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
            """,
            (installation_id, client_version, watchdog_version, client_status,
             watchdog_status, last_update_status, local_ip, observed_ip),
        )
        if target_status:
            _advance_target(cur, installation_id, target_version, target_status,
                            target_progress, target_error)
        _purge_old_heartbeats(cur, installation_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _advance_target(cur, installation_id, target_version, target_status,
                    target_progress, target_error):
    """Move the live target for this installation's store to the status the
    watchdog reports, then settle the rollout if every target is terminal."""
    cur.execute(
        "SELECT CAST(store_id AS VARCHAR(36)) FROM dbo.stock_client_installations WHERE installation_id = ?",
        (installation_id,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return
    store_id = row[0]
    active = ",".join(f"'{s}'" for s in (_ACTIVE_TARGET_STATUSES + ("FAILED",)))
    cur.execute(
        f"""
        SELECT TOP 1 CAST(t.id AS VARCHAR(36)), CAST(t.deployment_id AS VARCHAR(36))
        FROM dbo.stock_client_deployment_targets t
        JOIN dbo.stock_client_deployments d ON d.id = t.deployment_id
        WHERE t.store_id = ? AND d.status IN ('PENDING','IN_PROGRESS')
          AND t.status IN ({active})
          {"AND t.target_version = ?" if target_version else ""}
        ORDER BY t.updated_at DESC
        """,
        ((store_id, target_version) if target_version else (store_id,)),
    )
    hit = cur.fetchone()
    if not hit:
        return
    target_id, deployment_id = hit[0], hit[1]
    completed = ", completed_at = SYSUTCDATETIME()" if target_status in _TERMINAL_TARGET_STATUSES else ""
    cur.execute(
        f"""
        UPDATE dbo.stock_client_deployment_targets
        SET status = ?, progress = COALESCE(?, progress), error = ?,
            installation_id = COALESCE(installation_id, ?),
            started_at = COALESCE(started_at, SYSUTCDATETIME()),
            updated_at = SYSUTCDATETIME(){completed}
        WHERE id = ?
        """,
        (target_status, target_progress, target_error, installation_id, target_id),
    )
    _insert_event(cur, event_type="TARGET_PROGRESS",
                  installation_id=installation_id, deployment_id=deployment_id,
                  store_id=store_id, target_version=target_version,
                  detail=target_error, result=target_status)
    # In progress once any store starts; completed once none remain live.
    cur.execute(
        "UPDATE dbo.stock_client_deployments SET status = 'IN_PROGRESS' WHERE id = ? AND status = 'PENDING'",
        (deployment_id,),
    )
    cur.execute(
        f"""
        SELECT COUNT(*) FROM dbo.stock_client_deployment_targets
        WHERE deployment_id = ? AND status IN ({",".join("'" + s + "'" for s in _ACTIVE_TARGET_STATUSES)})
        """,
        (deployment_id,),
    )
    if cur.fetchone()[0] == 0:
        cur.execute(
            "UPDATE dbo.stock_client_deployments SET status = 'COMPLETED', completed_at = SYSUTCDATETIME() WHERE id = ? AND status = 'IN_PROGRESS'",
            (deployment_id,),
        )


def _purge_old_heartbeats(cur, installation_id):
    cur.execute(
        """
        DELETE FROM dbo.stock_client_heartbeats
        WHERE installation_id = ? AND heartbeat_id NOT IN (
            SELECT TOP (?) heartbeat_id FROM dbo.stock_client_heartbeats
            WHERE installation_id = ? ORDER BY heartbeat_id DESC
        )
        """,
        (installation_id, _HEARTBEAT_RETENTION, installation_id),
    )


def list_installations():
    """One row per store (LEFT JOIN from the store master so every store shows,
    even before its client has ever checked in), plus that store's current
    target version from the newest live deployment target."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        active = ",".join("'" + s + "'" for s in _ACTIVE_TARGET_STATUSES)
        cur.execute(
            f"""
            SELECT
                CAST(st.store_id AS VARCHAR(36)) AS store_id,
                st.store_code, st.store_name,
                CAST(i.tenant_id AS VARCHAR(36)) AS tenant_id,
                CAST(i.installation_id AS VARCHAR(36)) AS installation_id,
                i.client_version, i.watchdog_version,
                i.client_status, i.watchdog_status, i.last_update_status,
                i.local_ip, i.observed_ip, i.os_version, i.last_heartbeat_at,
                i.last_error, i.status AS installation_status,
                (SELECT TOP 1 t.target_version
                   FROM dbo.stock_client_deployment_targets t
                   JOIN dbo.stock_client_deployments d ON d.id = t.deployment_id
                  WHERE t.store_id = st.store_id AND t.status IN ({active})
                    AND d.status IN ('PENDING','IN_PROGRESS')
                  ORDER BY t.updated_at DESC) AS target_version
            FROM dbo.stores st
            LEFT JOIN dbo.stock_client_installations i ON i.store_id = st.store_id
            WHERE st.is_active = 1
            ORDER BY st.store_code
            """
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_installation(installation_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(i.installation_id AS VARCHAR(36)) AS installation_id,
                   CAST(i.tenant_id AS VARCHAR(36)) AS tenant_id,
                   CAST(i.store_id AS VARCHAR(36)) AS store_id,
                   st.store_code, st.store_name, i.device_id, i.fingerprint_hash,
                   i.hostname, i.local_ip, i.observed_ip, i.os_version,
                   i.client_version, i.watchdog_version, i.client_status,
                   i.watchdog_status, i.last_update_status, i.last_error,
                   i.last_heartbeat_at, i.registered_at, i.status
            FROM dbo.stock_client_installations i
            LEFT JOIN dbo.stores st ON st.store_id = i.store_id
            WHERE i.installation_id = ?
            """,
            (installation_id,),
        )
        rows = _rows_to_dicts(cur)
        if not rows:
            return None
        installation = rows[0]
        cur.execute(
            """
            SELECT TOP 40 event_type, actor, detail, target_version, result, created_at
            FROM dbo.stock_client_events
            WHERE installation_id = ? ORDER BY created_at DESC, event_id DESC
            """,
            (installation_id,),
        )
        installation["events"] = _rows_to_dicts(cur)
        return installation
    finally:
        conn.close()


def get_installation_state(installation_id):
    """The watchdog's poll: the live, AUTHORIZED target for this installation's
    store (if any). Returns the release manifest fields the watchdog needs to
    download + verify. None when nothing is pending."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT CAST(store_id AS VARCHAR(36)) FROM dbo.stock_client_installations WHERE installation_id = ?",
            (installation_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return {"target": None}
        store_id = row[0]
        active = ",".join("'" + s + "'" for s in _ACTIVE_TARGET_STATUSES)
        cur.execute(
            f"""
            SELECT TOP 1 t.target_version,
                   r.release_id, r.file_name, r.sha256, r.file_size, r.signature,
                   CAST(d.id AS VARCHAR(36)) AS deployment_id
            FROM dbo.stock_client_deployment_targets t
            JOIN dbo.stock_client_deployments d ON d.id = t.deployment_id
            JOIN dbo.stock_client_releases r ON r.version = t.target_version
            WHERE t.store_id = ? AND t.status IN ({active})
              AND d.status IN ('PENDING','IN_PROGRESS')
            ORDER BY t.updated_at DESC
            """,
            (store_id,),
        )
        rows = _rows_to_dicts(cur)
        if not rows:
            return {"target": None}
        r = rows[0]
        return {
            "target": {
                "target_version": r["target_version"],
                "release_id": r["release_id"],
                "sha256": (r["sha256"] or "").strip(),
                "file_size": r["file_size"],
                "signature": r["signature"],
                "download_url": f"/api/agent/stock-client/download/{r['target_version']}",
                "deployment_id": r["deployment_id"],
            }
        }
    finally:
        conn.close()
