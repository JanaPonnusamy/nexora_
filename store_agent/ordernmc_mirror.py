"""OrderNMC mirror (agent side): keep this PC's local OrderNMC in step with HO.

Device-mode only. HO decides everything (see backend/modules/ordernmc_mirror):
which device mirrors which HO OrderNMC, the local SQL connection (password
Fernet-encrypted like store DB passwords), the interval, and which rows changed.
This side just loops pull -> apply -> ack until HO says idle, then sleeps.

Local login: Windows auth first, then the HO-configured SQL login.

Apply rules (HO is the source of truth for every row it sends):
  * upsert  (table has a PK on HO): MERGE on the key -- insert new, update
    changed. Local rows HO does not have are never touched.
  * replace (HO table has no PK): rows are grouped by HO's natural key; each
    changed group is deleted locally and re-inserted from HO. Local rows whose
    key HO does not have are never touched.
  * A missing local table is created from HO's definition; missing columns are
    added (NULL). Nothing local is ever dropped.

A failed batch is rolled back and reported (HO parks that table for a while so
the rest keep flowing). Nothing here can raise out of the loop.

Manual run:  python -m store_agent.ordernmc_mirror --once
"""
import datetime
import decimal
import threading
import time
import traceback

import pyodbc
import requests

API = "/api/ordernmc-mirror/v1/agent"
STAGE = "#nexora_mirror_stage"
DISABLED_RECHECK_SECONDS = 300
ERROR_RETRY_SECONDS = 120
INSERT_CHUNK = 2000


def _safe_tb():
    try:
        return traceback.format_exc()
    except Exception:
        return "<traceback unavailable>"


def q(name):
    return "[" + str(name).replace("]", "]]") + "]"


# ---- value codec (inverse of backend catalog.encode_value) -----------------

def decode_value(sql_type_name, value):
    if value is None:
        return None
    t = sql_type_name
    if t in ("datetime", "datetime2", "smalldatetime", "datetimeoffset"):
        return datetime.datetime.fromisoformat(value)
    if t == "date":
        return datetime.date.fromisoformat(value)
    if t == "time":
        return datetime.time.fromisoformat(value)
    if t in ("decimal", "numeric", "money", "smallmoney"):
        return decimal.Decimal(value)
    if t in ("binary", "varbinary"):
        return bytes.fromhex(value)
    return value


# ---- HO client --------------------------------------------------------------

class MirrorClient:
    def __init__(self, device, timeout=300):
        self.device = device
        self.timeout = timeout

    def _request(self, method, path, **kwargs):
        from store_agent import config

        ho_url = config.active_ho_url()
        for attempt in (1, 2):
            token = self.device.get_token(ho_url)
            resp = requests.request(
                method, ho_url.rstrip("/") + API + path,
                headers={"Authorization": "Bearer " + token, "Accept-Encoding": "gzip"},
                timeout=self.timeout, **kwargs,
            )
            if resp.status_code == 401 and attempt == 1:
                self.device._token = None  # expired/rotated -> mint a fresh one
                continue
            return resp

    def config(self):
        resp = self._request("GET", "/config")
        if resp.status_code == 404:
            return {"enabled": False}  # HO build without the mirror: stay quiet
        resp.raise_for_status()
        return resp.json()

    def pull(self):
        resp = self._request("POST", "/pull")
        resp.raise_for_status()
        return resp.json()

    def ack(self, batch_id, ok=True, error=None):
        resp = self._request("POST", "/ack", json={"batch_id": batch_id, "ok": ok, "error": error})
        if resp.status_code == 409:
            return False  # batch expired/reset on HO; next pull re-sends
        resp.raise_for_status()
        return True


# ---- local target -----------------------------------------------------------

def _driver():
    from store_agent.sql_connection_factory import SqlConnectionFactory
    return SqlConnectionFactory()._get_driver()


def open_target(target):
    """pyodbc connection to the local OrderNMC described by HO's config."""
    password = None
    if target.get("password_encrypted"):
        from store_agent.fernet_key_service import FernetKeyService
        from store_agent.store_agent_config_decryption_service import (
            StoreAgentConfigDecryptionService,
        )
        password = StoreAgentConfigDecryptionService().decrypt_password(
            bytes.fromhex(target["password_encrypted"]), FernetKeyService().load_key()
        )
    base = [
        "DRIVER={" + _driver() + "}",
        "SERVER=" + target["server_name"],
        "DATABASE=" + (target.get("database_name") or "OrderNMC"),
        "TrustServerCertificate=yes",
    ]
    # Windows auth first (the agent service account); the HO-configured SQL
    # login is the fallback when that account has no access.
    attempts = [base + ["Trusted_Connection=yes"]]
    if target.get("username"):
        attempts.append(base + ["UID=" + target["username"], "PWD=" + (password or "")])
    last_error = None
    for parts in attempts:
        try:
            conn = pyodbc.connect(";".join(parts) + ";", timeout=15, autocommit=False)
        except pyodbc.Error as exc:
            last_error = exc
            continue
        conn.timeout = 600
        return conn
    raise last_error or RuntimeError("no connection attempt made")


class TargetApplier:
    def __init__(self, conn):
        self.conn = conn

    def _local_columns(self, cur, table):
        cur.execute(
            "SELECT c.name, c.is_identity, c.is_computed, TYPE_NAME(c.system_type_id), "
            "c.collation_name FROM sys.columns c WHERE c.object_id = OBJECT_ID(?)",
            "dbo." + q(table),
        )
        return {r[0].lower(): {"name": r[0], "identity": bool(r[1]),
                               "computed": bool(r[2]) or (r[3] or "").lower() == "timestamp",
                               "collation": r[4]}
                for r in cur.fetchall()}

    def ensure_table(self, cur, table, columns, pk_columns):
        """Create the table / add missing columns. Returns local column map."""
        local = self._local_columns(cur, table)
        if not local:
            defs = [f"{q(c['name'])} {c['sql_type']} {'NULL' if c['nullable'] else 'NOT NULL'}"
                    for c in columns]
            if pk_columns:
                defs.append(f"CONSTRAINT {q('PK_' + table)} PRIMARY KEY ("
                            + ", ".join(q(k) for k in pk_columns) + ")")
            cur.execute(f"CREATE TABLE [dbo].{q(table)} (" + ", ".join(defs) + ")")
            return self._local_columns(cur, table)
        added = False
        for c in columns:
            if c["name"].lower() not in local:
                cur.execute(f"ALTER TABLE [dbo].{q(table)} ADD {q(c['name'])} {c['sql_type']} NULL")
                added = True
        return self._local_columns(cur, table) if added else local

    def apply(self, batch):
        """Apply one HO batch in a single transaction. Returns rows sent."""
        table = batch["table"]
        columns = batch["columns"]
        keys = batch["key_columns"]
        cur = self.conn.cursor()
        try:
            local = self.ensure_table(cur, table, columns, batch.get("pk_columns") or [])
            idx = [i for i, c in enumerate(columns)
                   if c["name"].lower() in local and not local[c["name"].lower()]["computed"]]
            use = [columns[i] for i in idx]
            names = [c["name"] for c in use]
            lower = {n.lower() for n in names}
            missing_keys = [k for k in keys if k.lower() not in lower]
            if missing_keys:
                raise RuntimeError(f"{table}: local table cannot hold key column(s) {missing_keys}")

            stage_defs = [f"{q(c['name'])} {c['sql_type']}{_stage_collate(c, local)} NULL"
                          for c in use]
            cur.execute(f"IF OBJECT_ID('tempdb..{STAGE}') IS NOT NULL DROP TABLE {STAGE}")
            cur.execute(f"CREATE TABLE {STAGE} (" + ", ".join(stage_defs) + ")")

            types = [c["type"] for c in use]
            rows = [tuple(decode_value(types[j], r[i]) for j, i in enumerate(idx)) for r in batch["rows"]]
            has_max = any(c["sql_type"].endswith("(max)") for c in use)
            cur.fast_executemany = not has_max
            # Explicit sizes: otherwise pyodbc takes datetime/decimal precision
            # from the FIRST row, and a first value of hh:mm:ss.000 silently
            # truncates every later row's milliseconds.
            cur.setinputsizes([_input_size(c) for c in use])
            insert = (f"INSERT INTO {STAGE} (" + ", ".join(q(n) for n in names) + ") VALUES ("
                      + ", ".join("?" for _ in names) + ")")
            for start in range(0, len(rows), INSERT_CHUNK):
                cur.executemany(insert, rows[start:start + INSERT_CHUNK])
            cur.fast_executemany = False

            identity = [local[n.lower()]["name"] for n in names if local[n.lower()]["identity"]]
            if identity:
                cur.execute(f"SET IDENTITY_INSERT [dbo].{q(table)} ON")
            try:
                if batch["mode"] == "upsert":
                    cur.execute(_merge_sql(table, names, keys, set(n.lower() for n in identity)))
                else:
                    cur.execute(_replace_delete_sql(table, keys))
                    col_list = ", ".join(q(n) for n in names)
                    cur.execute(f"INSERT INTO [dbo].{q(table)} ({col_list}) SELECT {col_list} FROM {STAGE}")
            finally:
                if identity:
                    cur.execute(f"SET IDENTITY_INSERT [dbo].{q(table)} OFF")
            cur.execute(f"DROP TABLE {STAGE}")
            self.conn.commit()
            return len(rows)
        except Exception:
            try:
                self.conn.rollback()
            except Exception:
                pass
            raise


def _stage_collate(col, local):
    """COLLATE clause for a text staging column: the local table column's own
    collation (a remote OrderNMC can mix collations, e.g. CI_AI key columns in
    a CI_AS database, and the MERGE/DELETE key compare must not conflict)."""
    if col["type"] not in ("char", "varchar", "nchar", "nvarchar"):
        return ""
    name = (local.get(col["name"].lower()) or {}).get("collation")
    return f" COLLATE {name}" if name else " COLLATE DATABASE_DEFAULT"


def _type_args(sql_type_text):
    """'decimal(18,2)' -> [18, 2]; 'datetime2(7)' -> [7]; 'int' -> []."""
    if "(" not in sql_type_text:
        return []
    inner = sql_type_text[sql_type_text.index("(") + 1:-1]
    return [int(x) for x in inner.split(",") if x.strip().isdigit()]


def _input_size(col):
    t = col["type"]
    args = _type_args(col["sql_type"])
    if t == "datetime":
        return (pyodbc.SQL_TYPE_TIMESTAMP, 23, 3)
    if t == "smalldatetime":
        return (pyodbc.SQL_TYPE_TIMESTAMP, 16, 0)
    if t == "datetime2":
        scale = args[0] if args else 7
        return (pyodbc.SQL_TYPE_TIMESTAMP, 20 + scale if scale else 19, scale)
    if t in ("decimal", "numeric") and len(args) == 2:
        return (pyodbc.SQL_DECIMAL, args[0], args[1])
    if t == "money":
        return (pyodbc.SQL_DECIMAL, 19, 4)
    if t == "smallmoney":
        return (pyodbc.SQL_DECIMAL, 10, 4)
    return None


def _merge_sql(table, names, keys, identity_lower):
    key_lower = {k.lower() for k in keys}
    on = " AND ".join(f"T.{q(k)} = S.{q(k)}" for k in keys)
    partition = ", ".join(q(k) for k in keys)
    upd = [n for n in names if n.lower() not in key_lower and n.lower() not in identity_lower]
    col_list = ", ".join(q(n) for n in names)
    sql = (
        f"MERGE [dbo].{q(table)} AS T USING (SELECT {col_list} FROM ("
        f"SELECT *, ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY (SELECT 0)) AS __rn "
        f"FROM {STAGE}) AS x WHERE x.__rn = 1) AS S ON {on} "
    )
    if upd:
        s_cols = ", ".join(f"S.{q(n)}" for n in upd)
        t_cols = ", ".join(f"T.{q(n)}" for n in upd)
        sets = ", ".join(f"T.{q(n)} = S.{q(n)}" for n in upd)
        sql += f"WHEN MATCHED AND EXISTS (SELECT {s_cols} EXCEPT SELECT {t_cols}) THEN UPDATE SET {sets} "
    sql += (f"WHEN NOT MATCHED BY TARGET THEN INSERT ({col_list}) VALUES ("
            + ", ".join(f"S.{q(n)}" for n in names) + ");")
    return sql


def _replace_delete_sql(table, keys):
    t_keys = ", ".join(f"T.{q(k)}" for k in keys)
    s_keys = ", ".join(f"S.{q(k)}" for k in keys)
    return (
        f"DELETE T FROM [dbo].{q(table)} AS T WHERE EXISTS (SELECT 1 FROM {STAGE} AS S "
        f"WHERE EXISTS (SELECT {t_keys} INTERSECT SELECT {s_keys}))"
    )


# ---- loop ---------------------------------------------------------------------

def run_cycle(client, conn, log):
    """Pull/apply/ack until HO reports idle. Returns {table: rows applied}."""
    applier = TargetApplier(conn)
    applied = {}
    while True:
        batch = client.pull()
        status = batch.get("status")
        if status == "progress":
            continue
        if status != "batch":
            return applied
        try:
            n = applier.apply(batch)
        except Exception as exc:
            log(f"[MIRROR] {batch.get('table')}: apply failed:\n" + _safe_tb())
            client.ack(batch["batch_id"], ok=False, error=f"{type(exc).__name__}: {exc}"[:3900])
            continue
        client.ack(batch["batch_id"], ok=True)
        applied[batch["table"]] = applied.get(batch["table"], 0) + n


PURGE_EVERY_SECONDS = 6 * 3600
_last_purge = 0.0


def purge_retention(conn, rules, log):
    """Delete local rows older than the HO's retention window (batched, so the
    SIMPLE-recovery log stays small). Runs at most every PURGE_EVERY_SECONDS."""
    global _last_purge
    if not rules or time.time() - _last_purge < PURGE_EVERY_SECONDS:
        return
    _last_purge = time.time()
    cur = conn.cursor()
    for rule in rules:
        table, column, days = rule.get("table"), rule.get("column"), int(rule.get("days") or 0)
        if not table or not column or days <= 0:
            continue
        cur.execute("SELECT COL_LENGTH(?, ?)", f"dbo.{table}", column)
        if cur.fetchone()[0] is None:
            continue
        total = 0
        while True:
            cur.execute(f"DELETE TOP (20000) FROM [dbo].{q(table)} "
                        f"WHERE {q(column)} < DATEADD(day, -{days}, CAST(GETDATE() AS date))")
            n = cur.rowcount or 0
            conn.commit()
            total += n
            if n < 20000:
                break
        if total:
            log(f"[MIRROR] retention purged {total} {table} rows older than {days} days")


# OrderManagement holds only each store's CURRENT order (owner, 2026-11-06):
# older orders are moved into OrderManagementBackup for the remote user's compare.
ROLL_OM_SQL = """
SET NOCOUNT ON;
IF OBJECT_ID('dbo.OrderManagement') IS NULL OR OBJECT_ID('dbo.OrderManagementBackup') IS NULL RETURN;
DECLARE @cols nvarchar(max) = STUFF((
    SELECT ',' + QUOTENAME(c.name) FROM sys.columns c
    WHERE c.object_id = OBJECT_ID('dbo.OrderManagement') AND c.is_computed = 0
      AND EXISTS (SELECT 1 FROM sys.columns b WHERE b.object_id = OBJECT_ID('dbo.OrderManagementBackup')
                  AND b.name = c.name AND b.is_computed = 0 AND b.is_identity = 0)
    FOR XML PATH('')), 1, 1, '');
DECLARE @sql nvarchar(max) = N'
;WITH cur AS (SELECT StoreName, MAX(OrderId) AS OrderId FROM dbo.OrderManagement GROUP BY StoreName),
old AS (SELECT o.* FROM dbo.OrderManagement o JOIN cur ON cur.StoreName = o.StoreName WHERE o.OrderId < cur.OrderId)
INSERT INTO dbo.OrderManagementBackup (' + @cols + N') SELECT ' + @cols + N' FROM old
WHERE NOT EXISTS (SELECT 1 FROM dbo.OrderManagementBackup b WHERE b.StoreName = old.StoreName
                  AND b.OrderId = old.OrderId AND b.ProductCode = old.ProductCode);
DELETE o FROM dbo.OrderManagement o
JOIN (SELECT StoreName, MAX(OrderId) AS OrderId FROM dbo.OrderManagement GROUP BY StoreName) cur
  ON cur.StoreName = o.StoreName WHERE o.OrderId < cur.OrderId;
SELECT @@ROWCOUNT;';
EXEC sp_executesql @sql;
"""


def roll_order_management(conn, log):
    cur = conn.cursor()
    cur.execute(ROLL_OM_SQL)
    moved = 0
    while True:
        if cur.description:
            row = cur.fetchone()
            moved = int(row[0] or 0) if row else 0
        if not cur.nextset():
            break
    conn.commit()
    if moved:
        log(f"[MIRROR] moved {moved} older OrderManagement rows to OrderManagementBackup")


def run_forever(device, log):
    client = MirrorClient(device)
    while True:
        sleep_s = DISABLED_RECHECK_SECONDS
        conn = None
        try:
            cfg = client.config()
            if cfg.get("enabled"):
                sleep_s = int(cfg.get("interval_seconds") or 900)
                conn = open_target(cfg["target"])
                started = time.time()
                applied = run_cycle(client, conn, log)
                if applied:
                    log(f"[MIRROR] cycle applied {applied} in {int(time.time() - started)}s")
                try:
                    roll_order_management(conn, log)
                    purge_retention(conn, cfg.get("retention"), log)
                except Exception:
                    log("[MIRROR] retention purge failed:\n" + _safe_tb())
        except Exception:
            log("[MIRROR] cycle failed:\n" + _safe_tb())
            sleep_s = ERROR_RETRY_SECONDS
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        time.sleep(sleep_s)


def start_mirror_thread(device, log):
    def _target():
        while True:  # belt and braces: the loop itself never raises
            try:
                run_forever(device, log)
            except Exception:
                log("[MIRROR] loop crashed, restarting:\n" + _safe_tb())
                time.sleep(ERROR_RETRY_SECONDS)

    threading.Thread(target=_target, name="ordernmc-mirror", daemon=True).start()


if __name__ == "__main__":
    import sys

    from store_agent import config
    from store_agent.device_client import DeviceIdentity

    def _print(m):
        print(m, flush=True)

    dev = DeviceIdentity(config.DEVICE_STATE_DIR)
    if "--once" in sys.argv:
        mc = MirrorClient(dev)
        c = mc.config()
        if not c.get("enabled"):
            _print("[MIRROR] no enabled mirror target for this device")
        else:
            cn = open_target(c["target"])
            try:
                _print("[MIRROR] applied: " + str(run_cycle(mc, cn, _print)))
            finally:
                cn.close()
    else:
        run_forever(dev, _print)
