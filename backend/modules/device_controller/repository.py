"""SQL for the Device Controller module (SQL Server 2014-compatible: no
STRING_AGG / OPENJSON -- aggregation happens in Python)."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from config.database import get_connection

_SCHEMA_FILE = Path(__file__).with_name("sql") / "0001_device_controller.sql"
_schema_lock = Lock()
_schema_ready = False

ONLINE_SECONDS = 180


def ensure_schema():
    """Apply the idempotent DDL once per backend process (same pattern as
    modules/agent_ops)."""
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


def _rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def _one(cursor):
    rows = _rows(cursor)
    return rows[0] if rows else None


class _Conn:
    """`with _Conn() as cur:` -- commit on success, rollback on error."""

    def __enter__(self):
        ensure_schema()
        self.conn = get_connection()
        return self.conn.cursor()

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        return False


# ---- packages -------------------------------------------------------------

def release_meta_from_legacy_tables(app_key):
    """Integrity metadata recorded by the older publish flows, keyed by version."""
    sql = {
        "store_agent": "SELECT version, sha256, file_size, NULL AS signature FROM dbo.agent_releases",
        "stock_client": "SELECT version, sha256, file_size, signature FROM dbo.stock_client_releases",
    }.get(app_key)
    if not sql:
        return {}
    try:
        with _Conn() as cur:
            cur.execute(sql)
            return {r["version"]: r for r in _rows(cur)}
    except Exception:
        return {}  # table may not exist on a fresh database


def upsert_package(app_key, pkg, base_url):
    with _Conn() as cur:
        cur.execute("SELECT source_urls FROM dbo.dc_packages WHERE app_key = ? AND version = ?",
                    app_key, pkg["version"])
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """INSERT INTO dbo.dc_packages
                   (app_key, version, file_name, sha256, file_size, signature, source_urls)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                app_key, pkg["version"], pkg["file_name"], pkg["sha256"],
                int(pkg["file_size"]), pkg.get("signature"), base_url,
            )
            return
        urls = [u for u in (row[0] or "").split(",") if u]
        if base_url not in urls:
            urls.append(base_url)
        cur.execute(
            """UPDATE dbo.dc_packages SET file_name = ?, sha256 = ?, file_size = ?,
                      signature = COALESCE(?, signature), source_urls = ?
               WHERE app_key = ? AND version = ?""",
            pkg["file_name"], pkg["sha256"], int(pkg["file_size"]), pkg.get("signature"),
            ",".join(urls)[:1000], app_key, pkg["version"],
        )


def list_packages():
    with _Conn() as cur:
        cur.execute(
            """SELECT app_key, version, file_name, sha256, file_size, signature,
                      source_urls, registered_at
               FROM dbo.dc_packages ORDER BY app_key, registered_at DESC"""
        )
        return _rows(cur)


def get_package(app_key, version):
    with _Conn() as cur:
        cur.execute(
            """SELECT app_key, version, file_name, sha256, file_size, signature, source_urls
               FROM dbo.dc_packages WHERE app_key = ? AND version = ?""",
            app_key, version,
        )
        return _one(cur)


# ---- enrollment codes -----------------------------------------------------

def create_enroll_code(code, note, created_by, hours, max_uses):
    with _Conn() as cur:
        cur.execute(
            """INSERT INTO dbo.dc_enroll_codes (code, note, created_by, expires_at, max_uses)
               VALUES (?, ?, ?, DATEADD(hour, ?, SYSUTCDATETIME()), ?)""",
            code, note, created_by, int(hours), int(max_uses),
        )
        cur.execute("SELECT * FROM dbo.dc_enroll_codes WHERE code = ?", code)
        return _one(cur)


def list_enroll_codes():
    with _Conn() as cur:
        cur.execute(
            """SELECT TOP 50 code, note, created_by, created_at, expires_at, max_uses,
                      use_count, revoked,
                      CASE WHEN revoked = 0 AND expires_at > SYSUTCDATETIME()
                                AND use_count < max_uses THEN 1 ELSE 0 END AS usable
               FROM dbo.dc_enroll_codes ORDER BY created_at DESC"""
        )
        return _rows(cur)


def revoke_enroll_code(code):
    with _Conn() as cur:
        cur.execute("UPDATE dbo.dc_enroll_codes SET revoked = 1 WHERE code = ?", code)
        return cur.rowcount > 0


def consume_enroll_code(code):
    """Atomically use one slot of a valid code. Returns the code row or None."""
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.dc_enroll_codes SET use_count = use_count + 1
               WHERE code = ? AND revoked = 0 AND expires_at > SYSUTCDATETIME()
                 AND use_count < max_uses""",
            code,
        )
        if cur.rowcount != 1:
            return None
        cur.execute("SELECT * FROM dbo.dc_enroll_codes WHERE code = ?", code)
        return _one(cur)


# ---- devices + heartbeat --------------------------------------------------

def record_heartbeat(device_id, hb, observed_ip):
    apps_json = json.dumps(hb.get("apps") or [], default=str)
    with _Conn() as cur:
        cur.execute(
            """
            MERGE dbo.dc_devices AS t
            USING (SELECT CAST(? AS UNIQUEIDENTIFIER) AS device_id) AS s
            ON t.device_id = s.device_id
            WHEN MATCHED THEN UPDATE SET
                hostname = ?, local_ip = ?, observed_ip = ?, os_version = ?,
                controller_version = ?, ho_url = ?, apps_json = ?,
                last_heartbeat_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (device_id, hostname, local_ip, observed_ip, os_version,
                 controller_version, ho_url, apps_json, last_heartbeat_at)
                VALUES (s.device_id, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME());
            """,
            device_id,
            hb.get("hostname"), hb.get("local_ip"), observed_ip, hb.get("os_version"),
            hb.get("controller_version"), hb.get("ho_url"), apps_json,
            hb.get("hostname"), hb.get("local_ip"), observed_ip, hb.get("os_version"),
            hb.get("controller_version"), hb.get("ho_url"), apps_json,
        )
        cur.execute(
            "UPDATE dbo.device_registrations SET last_seen_at = SYSUTCDATETIME() WHERE device_id = ?",
            device_id,
        )


def get_desired(device_id):
    with _Conn() as cur:
        cur.execute(
            """SELECT app_key, desired_state, paused_until FROM dbo.dc_app_desired
               WHERE device_id = ?""",
            device_id,
        )
        return {r["app_key"]: r for r in _rows(cur)}


def set_desired(device_id, app_key, state, pause_minutes, actor):
    with _Conn() as cur:
        cur.execute(
            """
            MERGE dbo.dc_app_desired AS t
            USING (SELECT CAST(? AS UNIQUEIDENTIFIER) AS device_id, ? AS app_key) AS s
            ON t.device_id = s.device_id AND t.app_key = s.app_key
            WHEN MATCHED THEN UPDATE SET desired_state = ?,
                paused_until = CASE WHEN ? IS NULL THEN NULL
                                    ELSE DATEADD(minute, ?, SYSUTCDATETIME()) END,
                updated_by = ?, updated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT (device_id, app_key, desired_state, paused_until, updated_by)
                VALUES (s.device_id, s.app_key, ?,
                        CASE WHEN ? IS NULL THEN NULL
                             ELSE DATEADD(minute, ?, SYSUTCDATETIME()) END, ?);
            """,
            device_id, app_key,
            state, pause_minutes, pause_minutes, actor,
            state, pause_minutes, pause_minutes, actor,
        )


def resume_expired_pauses(device_id):
    """PAUSED rows whose pause window ended go back to RUNNING."""
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.dc_app_desired SET desired_state = 'RUNNING', paused_until = NULL,
                      updated_by = 'auto-resume', updated_at = SYSUTCDATETIME()
               WHERE device_id = ? AND desired_state = 'PAUSED'
                 AND paused_until IS NOT NULL AND paused_until <= SYSUTCDATETIME()""",
            device_id,
        )


def _device_select(where="", params=()):
    with _Conn() as cur:
        cur.execute(
            f"""
            SELECT r.device_id, r.machine_name, r.status AS registration_status,
                   r.app_version, r.registered_by_username, r.created_at AS registered_at,
                   d.hostname, d.local_ip, d.observed_ip, d.os_version, d.controller_version,
                   d.ho_url, d.apps_json, d.last_heartbeat_at,
                   CASE WHEN d.last_heartbeat_at > DATEADD(second, -{ONLINE_SECONDS}, SYSUTCDATETIME())
                        THEN 1 ELSE 0 END AS online,
                   (SELECT COUNT(*) FROM dbo.dc_commands c
                     WHERE c.device_id = r.device_id
                       AND c.status IN ('QUEUED', 'DELIVERED', 'RUNNING')) AS pending_commands
            FROM dbo.device_registrations r
            LEFT JOIN dbo.dc_devices d ON d.device_id = r.device_id
            WHERE (r.app_type = 'device_controller' OR d.device_id IS NOT NULL) {where}
            ORDER BY COALESCE(d.hostname, r.machine_name)
            """,
            *params,
        )
        devices = _rows(cur)
        cur.execute(
            """SELECT a.device_id, s.store_id, s.store_code, s.store_name
               FROM dbo.device_store_assignments a
               JOIN dbo.stores s ON s.store_id = a.store_id
               WHERE a.is_active = 1"""
        )
        stores = {}
        for row in _rows(cur):
            stores.setdefault(str(row["device_id"]).lower(), []).append(
                {"store_id": str(row["store_id"]), "store_code": row["store_code"],
                 "store_name": row["store_name"]})
        cur.execute("SELECT device_id, app_key, desired_state, paused_until FROM dbo.dc_app_desired")
        desired = {}
        for row in _rows(cur):
            desired.setdefault(str(row["device_id"]).lower(), {})[row["app_key"]] = {
                "desired_state": row["desired_state"], "paused_until": row["paused_until"]}
    for d in devices:
        key = str(d["device_id"]).lower()
        d["device_id"] = str(d["device_id"])
        d["online"] = bool(d["online"])
        try:
            d["apps"] = json.loads(d.pop("apps_json") or "[]")
        except ValueError:
            d["apps"] = []
        d["stores"] = stores.get(key, [])
        d["desired"] = desired.get(key, {})
    return devices


def list_devices():
    return _device_select()


def get_device(device_id):
    rows = _device_select("AND r.device_id = ?", (device_id,))
    return rows[0] if rows else None


def revoke_device(device_id):
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.device_registrations SET status = 'revoked',
                      revoked_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME()
               WHERE device_id = ?""",
            device_id,
        )
        return cur.rowcount > 0


# ---- commands -------------------------------------------------------------

def insert_command(command_id, device_id, app_key, action, args, payload, signature,
                   actor, expires_epoch):
    with _Conn() as cur:
        cur.execute(
            """INSERT INTO dbo.dc_commands
               (command_id, device_id, app_key, action, args_json, payload_json, signature,
                requested_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, DATEADD(second, ?, '1970-01-01'))""",
            command_id, device_id, app_key, action, json.dumps(args or {}),
            json.dumps(payload, sort_keys=True), signature, actor, int(expires_epoch),
        )
    return get_command(command_id)


_COMMAND_COLS = """command_id, device_id, app_key, action, args_json, status, requested_by,
                   requested_at, expires_at, delivered_at, started_at, finished_at,
                   exit_code, result_text"""


def _norm_command(row):
    if not row:
        return row
    row["command_id"] = str(row["command_id"])
    row["device_id"] = str(row["device_id"])
    try:
        row["args"] = json.loads(row.pop("args_json") or "{}")
    except ValueError:
        row["args"] = {}
    return row


def get_command(command_id):
    with _Conn() as cur:
        cur.execute(f"SELECT {_COMMAND_COLS} FROM dbo.dc_commands WHERE command_id = ?", command_id)
        return _norm_command(_one(cur))


def list_commands(device_id=None, limit=100):
    where = "WHERE device_id = ?" if device_id else ""
    params = (device_id,) if device_id else ()
    with _Conn() as cur:
        cur.execute(
            f"SELECT TOP {int(limit)} {_COMMAND_COLS} FROM dbo.dc_commands {where} "
            "ORDER BY requested_at DESC",
            *params,
        )
        return [_norm_command(r) for r in _rows(cur)]


def cancel_command(command_id, actor):
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.dc_commands SET status = 'CANCELLED', finished_at = SYSUTCDATETIME(),
                      result_text = ?
               WHERE command_id = ? AND status = 'QUEUED'""",
            f"cancelled by {actor}", command_id,
        )
        return cur.rowcount > 0


def record_command_result(device_id, command_id, status, exit_code, result_text):
    with _Conn() as cur:
        if status == "RUNNING":
            cur.execute(
                """UPDATE dbo.dc_commands SET status = 'RUNNING', started_at = SYSUTCDATETIME(),
                          result_text = COALESCE(?, result_text)
                   WHERE command_id = ? AND device_id = ?
                     AND status IN ('QUEUED', 'DELIVERED', 'RUNNING')""",
                result_text, command_id, device_id,
            )
        else:
            cur.execute(
                """UPDATE dbo.dc_commands SET status = ?, finished_at = SYSUTCDATETIME(),
                          started_at = COALESCE(started_at, SYSUTCDATETIME()),
                          exit_code = ?, result_text = ?
                   WHERE command_id = ? AND device_id = ?""",
                status, exit_code, (result_text or "")[:200000], command_id, device_id,
            )
        return cur.rowcount > 0


# ---- the device's inbox ---------------------------------------------------

def take_messages(device_id):
    """Everything HO has queued for this device, marked delivered in the same
    transaction (so two concurrent polls never both get a message). Returns a
    list of {payload, signature}."""
    out = []
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.dc_commands SET status = 'EXPIRED', finished_at = SYSUTCDATETIME()
               WHERE device_id = ? AND status IN ('QUEUED', 'DELIVERED')
                 AND expires_at <= SYSUTCDATETIME()""",
            device_id,
        )
        # A DELIVERED command the device never acknowledged (RUNNING) was lost
        # in transit -- resend it. Safe: the controller ignores an id it has
        # already seen, and acknowledges RUNNING as soon as it accepts one.
        cur.execute(
            """UPDATE dbo.dc_commands SET status = 'DELIVERED', delivered_at = SYSUTCDATETIME()
               OUTPUT INSERTED.payload_json, INSERTED.signature, INSERTED.requested_at
               WHERE device_id = ? AND expires_at > SYSUTCDATETIME()
                 AND (status = 'QUEUED'
                      OR (status = 'DELIVERED'
                          AND delivered_at < DATEADD(second, -90, SYSUTCDATETIME())))""",
            device_id,
        )
        cmds = cur.fetchall()
        for row in sorted(cmds, key=lambda r: r[2]):
            out.append({"payload": json.loads(row[0]), "signature": row[1]})

        cur.execute(
            """UPDATE dbo.dc_terminal_sessions SET open_delivered = 1
               OUTPUT INSERTED.open_payload_json, INSERTED.open_signature
               WHERE device_id = ? AND status = 'OPENING' AND open_delivered = 0""",
            device_id,
        )
        for row in cur.fetchall():
            out.append({"payload": json.loads(row[0]), "signature": row[1]})

        cur.execute(
            """UPDATE io SET delivered = 1
               OUTPUT INSERTED.seq, INSERTED.payload_json, INSERTED.signature
               FROM dbo.dc_terminal_io io
               JOIN dbo.dc_terminal_sessions s ON s.session_id = io.session_id
               WHERE s.device_id = ? AND io.direction = 'IN' AND io.delivered = 0
                 AND s.status IN ('OPENING', 'OPEN')""",
            device_id,
        )
        for row in sorted(cur.fetchall(), key=lambda r: r[0]):
            out.append({"payload": json.loads(row[1]), "signature": row[2]})

        cur.execute(
            """UPDATE dbo.dc_terminal_sessions SET close_delivered = 1
               OUTPUT INSERTED.close_payload_json, INSERTED.close_signature
               WHERE device_id = ? AND status = 'CLOSING' AND close_delivered = 0""",
            device_id,
        )
        for row in cur.fetchall():
            out.append({"payload": json.loads(row[0]), "signature": row[1]})
    return out


# ---- terminal -------------------------------------------------------------

def create_session(session_id, device_id, payload, signature, actor):
    with _Conn() as cur:
        cur.execute(
            """INSERT INTO dbo.dc_terminal_sessions
               (session_id, device_id, status, open_payload_json, open_signature, opened_by)
               VALUES (?, ?, 'OPENING', ?, ?, ?)""",
            session_id, device_id, json.dumps(payload, sort_keys=True), signature, actor,
        )
        cur.execute(
            "INSERT INTO dbo.dc_terminal_io (session_id, direction, data, actor) VALUES (?, 'SYS', ?, ?)",
            session_id, f"session opened by {actor}", actor,
        )
    return get_session(session_id)


_SESSION_COLS = """s.session_id, s.device_id, s.status, s.opened_by, s.opened_at, s.closed_at,
                   s.close_reason, COALESCE(d.hostname, r.machine_name) AS hostname"""


def _norm_session(row):
    if row:
        row["session_id"] = str(row["session_id"])
        row["device_id"] = str(row["device_id"])
    return row


def get_session(session_id):
    with _Conn() as cur:
        cur.execute(
            f"""SELECT {_SESSION_COLS} FROM dbo.dc_terminal_sessions s
                LEFT JOIN dbo.dc_devices d ON d.device_id = s.device_id
                LEFT JOIN dbo.device_registrations r ON r.device_id = s.device_id
                WHERE s.session_id = ?""",
            session_id,
        )
        return _norm_session(_one(cur))


def list_sessions(device_id=None, active_only=False, limit=100):
    clauses, params = [], []
    if device_id:
        clauses.append("s.device_id = ?")
        params.append(device_id)
    if active_only:
        clauses.append("s.status IN ('OPENING', 'OPEN', 'CLOSING')")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _Conn() as cur:
        cur.execute(
            f"""SELECT TOP {int(limit)} {_SESSION_COLS} FROM dbo.dc_terminal_sessions s
                LEFT JOIN dbo.dc_devices d ON d.device_id = s.device_id
                LEFT JOIN dbo.device_registrations r ON r.device_id = s.device_id
                {where} ORDER BY s.opened_at DESC""",
            *params,
        )
        return [_norm_session(r) for r in _rows(cur)]


def count_active_sessions(device_id):
    with _Conn() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM dbo.dc_terminal_sessions
               WHERE device_id = ? AND status IN ('OPENING', 'OPEN')""",
            device_id,
        )
        return int(cur.fetchone()[0])


def add_io(session_id, direction, data, actor=None, payload=None, signature=None):
    with _Conn() as cur:
        cur.execute(
            """INSERT INTO dbo.dc_terminal_io
               (session_id, direction, data, payload_json, signature, actor, delivered)
               OUTPUT INSERTED.seq
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            session_id, direction, data,
            json.dumps(payload, sort_keys=True) if payload else None, signature, actor,
            0 if direction == "IN" else 1,
        )
        return int(cur.fetchone()[0])


def add_output(session_id, device_id, chunks):
    """Device -> HO output. Verifies the session belongs to the device."""
    with _Conn() as cur:
        cur.execute(
            "SELECT status FROM dbo.dc_terminal_sessions WHERE session_id = ? AND device_id = ?",
            session_id, device_id,
        )
        row = cur.fetchone()
        if row is None:
            return False
        if row[0] == "OPENING":
            cur.execute(
                "UPDATE dbo.dc_terminal_sessions SET status = 'OPEN' WHERE session_id = ?",
                session_id,
            )
        for chunk in chunks:
            if chunk:
                cur.execute(
                    """INSERT INTO dbo.dc_terminal_io (session_id, direction, data, delivered)
                       VALUES (?, 'OUT', ?, 1)""",
                    session_id, chunk,
                )
        return True


def io_after(session_id, after_seq, limit=2000):
    with _Conn() as cur:
        cur.execute(
            f"""SELECT TOP {int(limit)} seq, direction, data, actor, created_at
                FROM dbo.dc_terminal_io WHERE session_id = ? AND seq > ?
                ORDER BY seq""",
            session_id, int(after_seq),
        )
        return _rows(cur)


def request_close(session_id, payload, signature, reason):
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.dc_terminal_sessions SET status = 'CLOSING',
                      close_payload_json = ?, close_signature = ?, close_reason = ?
               WHERE session_id = ? AND status IN ('OPENING', 'OPEN')""",
            json.dumps(payload, sort_keys=True), signature, reason, session_id,
        )
        return cur.rowcount > 0


def close_stale_sessions(stale_minutes=10):
    """Sessions whose device stopped heartbeating can never be closed by the
    device itself; close them so they don't show as live forever."""
    with _Conn() as cur:
        cur.execute(
            """UPDATE s SET status = 'CLOSED', closed_at = SYSUTCDATETIME(),
                      close_reason = COALESCE(s.close_reason, 'device offline')
               FROM dbo.dc_terminal_sessions s
               LEFT JOIN dbo.dc_devices d ON d.device_id = s.device_id
               WHERE s.status IN ('OPENING', 'OPEN', 'CLOSING')
                 AND s.opened_at < DATEADD(minute, -?, SYSUTCDATETIME())
                 AND (d.last_heartbeat_at IS NULL
                      OR d.last_heartbeat_at < DATEADD(minute, -?, SYSUTCDATETIME()))""",
            int(stale_minutes), int(stale_minutes),
        )


def mark_session_closed(session_id, device_id, reason):
    with _Conn() as cur:
        cur.execute(
            """UPDATE dbo.dc_terminal_sessions SET status = 'CLOSED', closed_at = SYSUTCDATETIME(),
                      close_reason = COALESCE(close_reason, ?)
               WHERE session_id = ? AND device_id = ? AND status <> 'CLOSED'""",
            reason, session_id, device_id,
        )
        if cur.rowcount:
            cur.execute(
                "INSERT INTO dbo.dc_terminal_io (session_id, direction, data, delivered) VALUES (?, 'SYS', ?, 1)",
                session_id, f"session closed ({reason})",
            )
