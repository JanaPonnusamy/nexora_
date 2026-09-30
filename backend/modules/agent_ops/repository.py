from pathlib import Path
from threading import Lock

from config.database import get_connection


_SCHEMA_FILE = Path(__file__).with_name("sql") / "0001_agent_ops.sql"
_schema_lock = Lock()
_schema_ready = False


def ensure_schema():
    """Apply the idempotent Agent Ops DDL once per backend process.

    The migration existed but was never connected to runtime startup/use. A
    partially provisioned database therefore accepted watchdog status updates
    and then failed every audit insert, rolling back the whole heartbeat and
    producing a large traceback every cycle on every store.
    """
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


def _rows_to_dicts(cursor):
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _insert_audit(cursor, store_id, event_type, detail=None, target_version=None):
    cursor.execute(
        """
        INSERT INTO dbo.agent_watchdog_audit
        (store_id, event_type, detail, target_version, created_at)
        VALUES (?, ?, ?, ?, SYSUTCDATETIME())
        """,
        (store_id, event_type, detail, target_version),
    )


def get_current_release():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 version, file_name, sha256, file_size, notes, released_at
            FROM dbo.agent_releases
            WHERE is_current = 1
            """
        )
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None
    finally:
        conn.close()


def get_watchdog_state(store_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT desired_state, desired_version
            FROM dbo.store_agent_registry
            WHERE store_id = ?
            """,
            (store_id,),
        )
        row = cur.fetchone()
        return {
            "desired_state": row[0] if row else "RUNNING",
            "desired_version": row[1] if row else None,
        }
    finally:
        conn.close()


def record_watchdog_heartbeat(store_id, watchdog_version, installed_agent_version,
                              service_state, last_action):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT last_action, installed_agent_version
            FROM dbo.agent_watchdog_status
            WHERE store_id = ?
            """,
            (store_id,),
        )
        previous = cur.fetchone()
        cur.execute(
            """
            UPDATE dbo.agent_watchdog_status
            SET watchdog_version = ?, installed_agent_version = ?,
                service_state = ?, last_action = ?, last_heartbeat = SYSUTCDATETIME()
            WHERE store_id = ?
            """,
            (watchdog_version, installed_agent_version, service_state,
             last_action, store_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO dbo.agent_watchdog_status
                (store_id, watchdog_version, installed_agent_version,
                 service_state, last_action, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME())
                """,
                (store_id, watchdog_version, installed_agent_version,
                 service_state, last_action),
            )
        previous_action = previous[0] if previous else None
        previous_version = previous[1] if previous else None
        if last_action and last_action != "no-op" and (
            last_action != previous_action or installed_agent_version != previous_version
        ):
            _insert_audit(
                cur,
                store_id,
                "WATCHDOG_ACTION",
                last_action,
                installed_agent_version,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_agent_ops(tenant_id=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        where = "WHERE st.tenant_id = ?" if tenant_id else ""
        params = (tenant_id,) if tenant_id else ()
        cur.execute(
            f"""
            SELECT
                CAST(st.store_id AS VARCHAR(36)) AS store_id,
                st.store_name,
                st.store_code,
                sar.agent_version,
                sar.connection_status,
                sar.last_heartbeat,
                sar.desired_state,
                sar.desired_version,
                ws.watchdog_version,
                ws.installed_agent_version,
                ws.service_state,
                ws.last_action,
                ws.last_heartbeat AS watchdog_last_heartbeat
            FROM dbo.stores st
            LEFT JOIN dbo.store_agent_registry sar ON sar.store_id = st.store_id
            LEFT JOIN dbo.agent_watchdog_status ws ON ws.store_id = st.store_id
            {where}
            ORDER BY st.store_name
            """,
            params,
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def list_releases():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT version, file_name, sha256, file_size, is_current, notes, released_at
            FROM dbo.agent_releases
            ORDER BY is_current DESC, released_at DESC, version DESC
            """
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def list_agent_logs(limit=100, store_id=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        params = [limit]
        where = ""
        if store_id:
            where = "WHERE a.store_id = ?"
            params.append(store_id)
        cur.execute(
            f"""
            SELECT TOP (?) a.audit_id,
                   CAST(a.store_id AS VARCHAR(36)) AS store_id,
                   st.store_code,
                   st.store_name,
                   a.event_type,
                   a.detail,
                   a.target_version,
                   a.created_at
            FROM dbo.agent_watchdog_audit a
            LEFT JOIN dbo.stores st ON st.store_id = a.store_id
            {where}
            ORDER BY a.created_at DESC, a.audit_id DESC
            """,
            params,
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def set_desired_state(store_ids, desired_state):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        updated = 0
        for store_id in store_ids:
            cur.execute(
                """
                UPDATE dbo.store_agent_registry
                SET desired_state = ?
                WHERE store_id = ?
                """,
                (desired_state, store_id),
            )
            if cur.rowcount:
                updated += cur.rowcount
                _insert_audit(cur, store_id, "DESIRED_STATE", desired_state, None)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_desired_version(store_ids, desired_version):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        updated = 0
        for store_id in store_ids:
            cur.execute(
                """
                UPDATE dbo.store_agent_registry
                SET desired_version = ?
                WHERE store_id = ?
                """,
                (desired_version, store_id),
            )
            if cur.rowcount:
                updated += cur.rowcount
                _insert_audit(
                    cur,
                    store_id,
                    "DESIRED_VERSION",
                    "follow-current" if desired_version is None else "pin-version",
                    desired_version,
                )
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def publish_release(version, file_name, sha256, file_size, notes=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dbo.agent_releases SET is_current = 0 WHERE is_current = 1")
        cur.execute(
            """
            MERGE dbo.agent_releases AS T
            USING (SELECT ? AS version) AS S ON T.version = S.version
            WHEN MATCHED THEN UPDATE SET
                file_name = ?, sha256 = ?, file_size = ?, notes = ?, is_current = 1
            WHEN NOT MATCHED THEN INSERT
                (version, file_name, sha256, file_size, notes, is_current)
                VALUES (?, ?, ?, ?, ?, 1);
            """,
            (version, file_name, sha256, file_size, notes,
             version, file_name, sha256, file_size, notes),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_release(version):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT version, file_name, sha256, file_size, notes, released_at
            FROM dbo.agent_releases
            WHERE version = ?
            """,
            (version,),
        )
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None
    finally:
        conn.close()
