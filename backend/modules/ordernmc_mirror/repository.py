"""Data access for the OrderNMC mirror.

Two databases:
  * NEXORA_PLATFORM  dbo.ordernmc_mirror_targets  -- device -> source + remote
    SQL connection (password Fernet-encrypted like dbo.stores).
  * SOURCE OrderNMC  nexora_mirror.*               -- per-target ledger of row
    hashes the target acknowledged, pass state, and in-flight batches.
"""
from __future__ import annotations

import json
import threading
import uuid

import pyodbc

from config.database import get_connection as _platform

# ---- NEXORA_PLATFORM: targets ---------------------------------------------

_platform_ready = False
_platform_lock = threading.Lock()

_TARGET_COLS = (
    "target_id, device_id, source_name, server_name, database_name, username, "
    "password_encrypted, interval_seconds, tables, is_enabled, last_pull_at, "
    "last_ack_at, last_error, updated_at, stores"
)


def ensure_platform_schema():
    global _platform_ready
    if _platform_ready:
        return
    with _platform_lock:
        if _platform_ready:
            return
        conn = _platform()
        try:
            conn.cursor().execute(
                """
                IF OBJECT_ID('dbo.ordernmc_mirror_targets', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ordernmc_mirror_targets (
                        target_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ordernmc_mirror_targets PRIMARY KEY,
                        device_id UNIQUEIDENTIFIER NOT NULL,
                        source_name NVARCHAR(50) NOT NULL,
                        server_name NVARCHAR(200) NOT NULL,
                        database_name NVARCHAR(128) NOT NULL CONSTRAINT DF_omt_db DEFAULT ('OrderNMC'),
                        username NVARCHAR(128) NULL,
                        password_encrypted VARBINARY(MAX) NULL,
                        interval_seconds INT NOT NULL CONSTRAINT DF_omt_interval DEFAULT (900),
                        tables NVARCHAR(MAX) NULL,
                        is_enabled BIT NOT NULL CONSTRAINT DF_omt_enabled DEFAULT (1),
                        last_pull_at DATETIME2(0) NULL,
                        last_ack_at DATETIME2(0) NULL,
                        last_error NVARCHAR(2000) NULL,
                        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_omt_created DEFAULT SYSUTCDATETIME(),
                        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_omt_updated DEFAULT SYSUTCDATETIME()
                    );
                    CREATE UNIQUE INDEX UX_ordernmc_mirror_targets_device
                        ON dbo.ordernmc_mirror_targets(device_id);
                END;
                IF COL_LENGTH('dbo.ordernmc_mirror_targets', 'stores') IS NULL
                    ALTER TABLE dbo.ordernmc_mirror_targets ADD stores NVARCHAR(MAX) NULL;
                """
            )
            conn.commit()
            _platform_ready = True
        finally:
            conn.close()


def _target_row(r) -> dict:
    return {
        "target_id": r[0], "device_id": str(r[1]), "source_name": r[2],
        "server_name": r[3], "database_name": r[4], "username": r[5],
        "password_encrypted": bytes(r[6]) if r[6] else None,
        "interval_seconds": r[7], "tables": r[8], "is_enabled": bool(r[9]),
        "last_pull_at": r[10], "last_ack_at": r[11], "last_error": r[12],
        "updated_at": r[13], "stores": r[14],
    }


def _valid_guid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def get_target_by_device(device_id):
    if not _valid_guid(device_id):
        return None
    ensure_platform_schema()
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {_TARGET_COLS} FROM dbo.ordernmc_mirror_targets WHERE device_id = ?", str(device_id))
        r = cur.fetchone()
        return _target_row(r) if r else None
    finally:
        conn.close()


def get_target(target_id):
    ensure_platform_schema()
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {_TARGET_COLS} FROM dbo.ordernmc_mirror_targets WHERE target_id = ?", int(target_id))
        r = cur.fetchone()
        return _target_row(r) if r else None
    finally:
        conn.close()


def list_targets():
    ensure_platform_schema()
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {_TARGET_COLS} FROM dbo.ordernmc_mirror_targets ORDER BY target_id")
        return [_target_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def upsert_target(device_id, source_name, server_name, database_name, username,
                  password_encrypted, interval_seconds, tables, is_enabled, stores=None):
    """Create/update the device's target. password_encrypted=None keeps the
    stored password. Returns target_id."""
    ensure_platform_schema()
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute("SELECT target_id FROM dbo.ordernmc_mirror_targets WHERE device_id = ?", str(device_id))
        r = cur.fetchone()
        if r:
            cur.execute(
                "UPDATE dbo.ordernmc_mirror_targets SET source_name = ?, server_name = ?, "
                "database_name = ?, username = ?, "
                "password_encrypted = CASE WHEN ? = 1 THEN ? ELSE password_encrypted END, "
                "interval_seconds = ?, tables = ?, is_enabled = ?, stores = ?, updated_at = SYSUTCDATETIME() "
                "WHERE target_id = ?",
                source_name, server_name, database_name, username,
                1 if password_encrypted is not None else 0,
                pyodbc.Binary(password_encrypted) if password_encrypted is not None else None,
                int(interval_seconds), tables, 1 if is_enabled else 0, stores, r[0],
            )
            target_id = r[0]
        else:
            cur.execute(
                "INSERT INTO dbo.ordernmc_mirror_targets (device_id, source_name, server_name, "
                "database_name, username, password_encrypted, interval_seconds, tables, is_enabled, stores) "
                "OUTPUT INSERTED.target_id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                str(device_id), source_name, server_name, database_name, username,
                pyodbc.Binary(password_encrypted) if password_encrypted is not None else None,
                int(interval_seconds), tables, 1 if is_enabled else 0, stores,
            )
            target_id = cur.fetchone()[0]
        conn.commit()
        return target_id
    finally:
        conn.close()


def delete_target(target_id):
    ensure_platform_schema()
    conn = _platform()
    try:
        conn.cursor().execute("DELETE FROM dbo.ordernmc_mirror_targets WHERE target_id = ?", int(target_id))
        conn.commit()
    finally:
        conn.close()


def touch_target(target_id, *, pulled=False, acked=False, error=None, clear_error=False):
    sets = []
    params = []
    if pulled:
        sets.append("last_pull_at = SYSUTCDATETIME()")
    if acked:
        sets.append("last_ack_at = SYSUTCDATETIME()")
    if error is not None:
        sets.append("last_error = ?")
        params.append(str(error)[:2000])
    elif clear_error:
        sets.append("last_error = NULL")
    if not sets:
        return
    conn = _platform()
    try:
        conn.cursor().execute(
            f"UPDATE dbo.ordernmc_mirror_targets SET {', '.join(sets)} WHERE target_id = ?",
            *params, int(target_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---- SOURCE OrderNMC: nexora_mirror.* -------------------------------------

_source_ready = set()
_source_lock = threading.Lock()

_SOURCE_DDL = """
IF SCHEMA_ID('nexora_mirror') IS NULL EXEC('CREATE SCHEMA nexora_mirror');

IF OBJECT_ID('nexora_mirror.table_ids', 'U') IS NULL
    CREATE TABLE nexora_mirror.table_ids (
        table_id SMALLINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_nexora_mirror_table_ids PRIMARY KEY,
        table_name NVARCHAR(128) NOT NULL CONSTRAINT UX_nexora_mirror_table_ids UNIQUE
    );

IF OBJECT_ID('nexora_mirror.ledger', 'U') IS NULL
    CREATE TABLE nexora_mirror.ledger (
        target_id INT NOT NULL,
        table_id SMALLINT NOT NULL,
        ph BINARY(8) NOT NULL,
        rh BINARY(8) NOT NULL,
        CONSTRAINT PK_nexora_mirror_ledger PRIMARY KEY (target_id, table_id, ph)
    );

IF OBJECT_ID('nexora_mirror.table_state', 'U') IS NULL
    CREATE TABLE nexora_mirror.table_state (
        target_id INT NOT NULL,
        table_id SMALLINT NOT NULL,
        cursor_json NVARCHAR(MAX) NULL,
        pass_started_at DATETIME NULL,
        last_pass_started_at DATETIME NULL,
        last_pass_completed_at DATETIME NULL,
        rows_sent BIGINT NOT NULL CONSTRAINT DF_nexora_mirror_state_rows DEFAULT (0),
        error_until DATETIME NULL,
        last_error NVARCHAR(2000) NULL,
        updated_at DATETIME NOT NULL CONSTRAINT DF_nexora_mirror_state_upd DEFAULT GETDATE(),
        CONSTRAINT PK_nexora_mirror_table_state PRIMARY KEY (target_id, table_id)
    );

IF OBJECT_ID('nexora_mirror.batch', 'U') IS NULL
    CREATE TABLE nexora_mirror.batch (
        batch_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_nexora_mirror_batch PRIMARY KEY,
        target_id INT NOT NULL,
        table_id SMALLINT NOT NULL,
        cursor_json NVARCHAR(MAX) NULL,
        pass_started_at DATETIME NOT NULL,
        is_last BIT NOT NULL,
        row_count INT NOT NULL,
        created_at DATETIME NOT NULL CONSTRAINT DF_nexora_mirror_batch_created DEFAULT GETDATE()
    );

IF OBJECT_ID('nexora_mirror.batch_item', 'U') IS NULL
    CREATE TABLE nexora_mirror.batch_item (
        batch_id UNIQUEIDENTIFIER NOT NULL,
        ph BINARY(8) NOT NULL,
        rh BINARY(8) NOT NULL,
        CONSTRAINT PK_nexora_mirror_batch_item PRIMARY KEY (batch_id, ph)
    );
"""


def ensure_source_schema(conn, source_name):
    key = (source_name or "").lower()
    if key in _source_ready:
        return
    with _source_lock:
        if key in _source_ready:
            return
        cur = conn.cursor()
        for stmt in _SOURCE_DDL.split("\n\n"):
            if stmt.strip():
                cur.execute(stmt)
        conn.commit()
        _source_ready.add(key)


def table_ids(conn, names) -> dict:
    """{table_name: table_id}, registering new names."""
    cur = conn.cursor()
    cur.execute("SELECT table_name, table_id FROM nexora_mirror.table_ids")
    ids = {r[0].lower(): r[1] for r in cur.fetchall()}
    missing = [n for n in names if n.lower() not in ids]
    for n in missing:
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM nexora_mirror.table_ids WHERE table_name = ?) "
            "INSERT INTO nexora_mirror.table_ids (table_name) VALUES (?)", n, n,
        )
    if missing:
        conn.commit()
        cur.execute("SELECT table_name, table_id FROM nexora_mirror.table_ids")
        ids = {r[0].lower(): r[1] for r in cur.fetchall()}
    return {n: ids[n.lower()] for n in names}


def server_clock(conn):
    """(now, sqlserver_start_time) in the source server's local time -- the
    clock sys.dm_db_index_usage_stats uses."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT GETDATE(), sqlserver_start_time FROM sys.dm_os_sys_info")
        r = cur.fetchone()
        return r[0], r[1]
    except Exception:
        cur.execute("SELECT GETDATE()")
        return cur.fetchone()[0], None


def load_states(conn, target_id) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT table_id, cursor_json, pass_started_at, last_pass_started_at, "
        "last_pass_completed_at, rows_sent, error_until, last_error "
        "FROM nexora_mirror.table_state WHERE target_id = ?", int(target_id),
    )
    return {r[0]: {
        "cursor": json.loads(r[1]) if r[1] else None, "pass_started_at": r[2],
        "last_pass_started_at": r[3], "last_pass_completed_at": r[4],
        "rows_sent": r[5], "error_until": r[6], "last_error": r[7],
    } for r in cur.fetchall()}


_STATE_MERGE = (
    "MERGE nexora_mirror.table_state AS s "
    "USING (SELECT ? AS target_id, ? AS table_id) AS k "
    "ON s.target_id = k.target_id AND s.table_id = k.table_id "
    "WHEN MATCHED THEN UPDATE SET {sets}, updated_at = GETDATE() "
    "WHEN NOT MATCHED THEN INSERT (target_id, table_id, {cols}) VALUES (k.target_id, k.table_id, {vals});"
)


def _set_state(cur, target_id, table_id, **fields):
    names = list(fields)
    sql = _STATE_MERGE.format(
        sets=", ".join(f"{n} = ?" for n in names),
        cols=", ".join(names), vals=", ".join("?" for _ in names),
    )
    vals = [fields[n] for n in names]
    cur.execute(sql, int(target_id), int(table_id), *vals, *vals)


def save_progress(conn, target_id, table_id, cursor, pass_started_at):
    _set_state(conn.cursor(), target_id, table_id,
               cursor_json=json.dumps(cursor) if cursor is not None else None,
               pass_started_at=pass_started_at)
    conn.commit()


def complete_pass(conn, target_id, table_id, pass_started_at, cur=None):
    own = cur is None
    cur = cur or conn.cursor()
    cur.execute("SELECT GETDATE()")
    now = cur.fetchone()[0]
    _set_state(cur, target_id, table_id, cursor_json=None, pass_started_at=None,
               last_pass_started_at=pass_started_at, last_pass_completed_at=now,
               error_until=None, last_error=None)
    if own:
        conn.commit()


def mark_due(conn, target_id, table_ids_=None):
    """Make the next pull re-verify these tables now ("push"). The ledger is
    kept, so only rows that differ from what the target already has are sent;
    a pass already in progress just carries on."""
    cur = conn.cursor()
    sql = ("UPDATE nexora_mirror.table_state SET last_pass_completed_at = NULL, "
           "error_until = NULL WHERE target_id = ? AND pass_started_at IS NULL")
    params = [int(target_id)]
    if table_ids_:
        sql += " AND table_id IN (" + ",".join("?" * len(table_ids_)) + ")"
        params += [int(t) for t in table_ids_]
    cur.execute(sql, params)
    n = cur.rowcount
    conn.commit()
    return n


def purge_stale_batches(conn, target_id, older_than_hours=24):
    cur = conn.cursor()
    cur.execute(
        "DELETE bi FROM nexora_mirror.batch_item bi JOIN nexora_mirror.batch b ON b.batch_id = bi.batch_id "
        "WHERE b.target_id = ? AND b.created_at < DATEADD(hour, ?, GETDATE())",
        int(target_id), -int(older_than_hours),
    )
    cur.execute(
        "DELETE FROM nexora_mirror.batch WHERE target_id = ? AND created_at < DATEADD(hour, ?, GETDATE())",
        int(target_id), -int(older_than_hours),
    )
    conn.commit()


def save_batch(conn, target_id, table_id, cursor, pass_started_at, is_last, items) -> str:
    """Persist an in-flight batch + its (ph, rh) items; returns batch_id."""
    batch_id = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO nexora_mirror.batch (batch_id, target_id, table_id, cursor_json, "
        "pass_started_at, is_last, row_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
        batch_id, int(target_id), int(table_id),
        json.dumps(cursor) if cursor is not None else None,
        pass_started_at, 1 if is_last else 0, len(items),
    )
    if items:
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO nexora_mirror.batch_item (batch_id, ph, rh) VALUES (?, ?, ?)",
            [(batch_id, pyodbc.Binary(ph), pyodbc.Binary(rh)) for ph, rh in items],
        )
    conn.commit()
    return batch_id


def get_batch(conn, batch_id):
    try:
        uuid.UUID(str(batch_id))
    except (ValueError, TypeError):
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT batch_id, target_id, table_id, cursor_json, pass_started_at, is_last, row_count "
        "FROM nexora_mirror.batch WHERE batch_id = ?", str(batch_id),
    )
    r = cur.fetchone()
    if not r:
        return None
    return {"batch_id": str(r[0]), "target_id": r[1], "table_id": r[2],
            "cursor": json.loads(r[3]) if r[3] else None,
            "pass_started_at": r[4], "is_last": bool(r[5]), "row_count": r[6]}


def _drop_batch(cur, batch_id):
    cur.execute("DELETE FROM nexora_mirror.batch_item WHERE batch_id = ?", batch_id)
    cur.execute("DELETE FROM nexora_mirror.batch WHERE batch_id = ?", batch_id)


def commit_batch(conn, batch):
    """The target applied the batch: fold its hashes into the ledger and
    advance the table's pass -- one transaction."""
    cur = conn.cursor()
    try:
        cur.execute(
            "MERGE nexora_mirror.ledger AS l "
            "USING (SELECT ph, MAX(rh) AS rh FROM nexora_mirror.batch_item WHERE batch_id = ? GROUP BY ph) AS b "
            "ON l.target_id = ? AND l.table_id = ? AND l.ph = b.ph "
            "WHEN MATCHED AND l.rh <> b.rh THEN UPDATE SET rh = b.rh "
            "WHEN NOT MATCHED THEN INSERT (target_id, table_id, ph, rh) VALUES (?, ?, b.ph, b.rh);",
            batch["batch_id"], batch["target_id"], batch["table_id"],
            batch["target_id"], batch["table_id"],
        )
        if batch["is_last"]:
            complete_pass(conn, batch["target_id"], batch["table_id"], batch["pass_started_at"], cur=cur)
        else:
            _set_state(cur, batch["target_id"], batch["table_id"],
                       cursor_json=json.dumps(batch["cursor"]) if batch["cursor"] is not None else None,
                       pass_started_at=batch["pass_started_at"], error_until=None, last_error=None)
        cur.execute(
            "UPDATE nexora_mirror.table_state SET rows_sent = rows_sent + ? WHERE target_id = ? AND table_id = ?",
            int(batch["row_count"]), batch["target_id"], batch["table_id"],
        )
        _drop_batch(cur, batch["batch_id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def fail_batch(conn, batch, error, backoff_minutes=30):
    """The target could not apply the batch: keep the pass where it is, park
    the table for a while so other tables keep flowing, record why."""
    cur = conn.cursor()
    _set_state(cur, batch["target_id"], batch["table_id"],
               error_until=None, last_error=str(error)[:2000])
    cur.execute(
        "UPDATE nexora_mirror.table_state SET error_until = DATEADD(minute, ?, GETDATE()) "
        "WHERE target_id = ? AND table_id = ?",
        int(backoff_minutes), batch["target_id"], batch["table_id"],
    )
    _drop_batch(cur, batch["batch_id"])
    conn.commit()


def ledger_counts(conn, target_id) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT table_id, COUNT_BIG(*) FROM nexora_mirror.ledger WHERE target_id = ? GROUP BY table_id",
        int(target_id),
    )
    return {r[0]: int(r[1]) for r in cur.fetchall()}


def reset_target(conn, target_id, table_ids_=None):
    """Forget everything the target acknowledged (all tables, or some) so the
    next passes re-send every row. Chunked to keep the log small."""
    cur = conn.cursor()
    scope = ""
    params = [int(target_id)]
    if table_ids_:
        scope = " AND table_id IN (" + ",".join("?" for _ in table_ids_) + ")"
        params += [int(t) for t in table_ids_]
    while True:
        cur.execute(f"DELETE TOP (50000) FROM nexora_mirror.ledger WHERE target_id = ?{scope}", *params)
        n = cur.rowcount
        conn.commit()
        if n <= 0:
            break
    cur.execute(f"DELETE FROM nexora_mirror.table_state WHERE target_id = ?{scope}", *params)
    cur.execute(
        f"DELETE bi FROM nexora_mirror.batch_item bi JOIN nexora_mirror.batch b ON b.batch_id = bi.batch_id "
        f"WHERE b.target_id = ?{scope.replace('table_id', 'b.table_id')}", *params,
    )
    cur.execute(f"DELETE FROM nexora_mirror.batch WHERE target_id = ?{scope}", *params)
    conn.commit()
