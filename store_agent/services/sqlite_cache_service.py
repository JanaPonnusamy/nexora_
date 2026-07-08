import json
import os
import sqlite3
import time
from pathlib import Path


class SqliteCacheService:
    """SYNC-040 V2 SQLite Cache Engine.

    Durable per-store cache enabling true delta sync:
      - sync_row_cache      : last-known row hash per (table, source_pk)
      - sync_table_state    : per-table watermark + last full/incremental sync
      - sync_pending_chunks : outbox for offline-HO recovery
      - sync_execution_log  : per-table per-execution delta metrics
    """

    def __init__(self, db_path=None, store_id=None):
        if db_path is None:
            # Under a frozen (PyInstaller onefile) build, __file__ resolves inside
            # the exe's throwaway per-launch extraction temp dir, which would wipe
            # this cache on every restart. NEXORA_INSTALL_PATH (set by the service
            # wrapper from sys.executable's real, persistent location) takes
            # priority so the cache survives restarts; __file__-relative stays as
            # the dev/source-mode fallback.
            install_path = os.environ.get("NEXORA_INSTALL_PATH")
            if install_path:
                db_path = Path(install_path) / "cache" / "store_agent.db"
            else:
                db_path = (
                    Path(__file__).resolve().parent.parent
                    / "config_cache"
                    / "store_agent.db"
                )
        self.db_path = str(db_path)
        # Cache identity is (store_id, table_name, source_pk). Every store using
        # the shared runtime DB MUST scope its cache by store_id, otherwise rows
        # synced by one store are seen as "already synced" by another.
        self.store_id = "__default__" if store_id is None else str(store_id)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            # Migrate any pre-existing store-unaware tables first, so the
            # CREATE TABLE IF NOT EXISTS below only ever runs for fresh installs.
            self._migrate_store_aware(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sync_row_cache (
                    store_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    source_pk TEXT NOT NULL,
                    row_hash TEXT NOT NULL,
                    last_sync_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (store_id, table_name, source_pk)
                );

                CREATE TABLE IF NOT EXISTS sync_table_state (
                    store_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    last_full_sync TEXT,
                    last_incremental_sync TEXT,
                    last_watermark TEXT,
                    PRIMARY KEY (store_id, table_name)
                );

                CREATE TABLE IF NOT EXISTS sync_pending_chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT,
                    table_name TEXT,
                    chunk_no INTEGER,
                    payload TEXT,
                    total_rows INTEGER,
                    sync_type TEXT,
                    status TEXT DEFAULT 'PENDING',
                    created_on TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sync_execution_log (
                    execution_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    rows_examined INTEGER DEFAULT 0,
                    rows_changed INTEGER DEFAULT 0,
                    rows_uploaded INTEGER DEFAULT 0,
                    rows_skipped INTEGER DEFAULT 0,
                    created_on TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (execution_id, table_name)
                );

                CREATE TABLE IF NOT EXISTS sync_watermark (
                    table_name TEXT PRIMARY KEY,
                    watermark_value TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS agent_configuration (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sync_table_config (
                    sync_table_id TEXT PRIMARY KEY,
                    table_name TEXT,
                    sync_mode TEXT,
                    watermark_column TEXT,
                    window_days INTEGER,
                    window_months INTEGER,
                    custom_where TEXT,
                    sync_order INTEGER,
                    is_active INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS sync_column_config (
                    sync_table_id TEXT,
                    table_name TEXT,
                    column_name TEXT,
                    data_type TEXT,
                    is_selected INTEGER,
                    is_pk INTEGER,
                    is_hash INTEGER,
                    is_watermark INTEGER,
                    column_order INTEGER,
                    PRIMARY KEY (sync_table_id, column_name)
                );

                CREATE TABLE IF NOT EXISTS sync_execution (
                    execution_id TEXT PRIMARY KEY,
                    status TEXT,
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS sync_ack (
                    chunk_execution_id INTEGER PRIMARY KEY,
                    execution_id TEXT,
                    table_name TEXT,
                    chunk_no INTEGER,
                    acked_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS schema_catalog (
                    schema_name TEXT,
                    table_name TEXT,
                    column_name TEXT,
                    data_type TEXT,
                    max_length INTEGER,
                    precision_value INTEGER,
                    scale_value INTEGER,
                    is_nullable INTEGER,
                    is_identity INTEGER,
                    is_primary_key INTEGER,
                    catalog_hash TEXT,
                    PRIMARY KEY (schema_name, table_name, column_name)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ---- schema migration (store-aware cache) -----------------------------

    @staticmethod
    def _table_exists(conn, table):
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        return cur.fetchone() is not None

    @staticmethod
    def _has_column(conn, table, column):
        cur = conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cur.fetchall())

    def _migrate_store_aware(self, conn):
        """Upgrade legacy store-unaware caches to (store_id, table_name, ...).

        The legacy cache merged every store's rows under a single
        (table_name, source_pk) identity, so its contents are cross-store
        contaminated and cannot be safely attributed to any one store. We drop
        and recreate the affected tables; row hashes and watermarks are a
        derived cache (re-computed on the next sync), never a source of truth.
        The first sync after migration becomes a clean full upload per store,
        then incremental deltas resume normally.
        """
        migrated = []
        for table in ("sync_row_cache", "sync_table_state"):
            if self._table_exists(conn, table) and not self._has_column(
                conn, table, "store_id"
            ):
                conn.execute(f"DROP TABLE {table}")
                migrated.append(table)
        if migrated:
            conn.commit()
            print(
                "[CACHE-MIGRATION] store-aware upgrade: rebuilt "
                + ", ".join(migrated)
                + " (legacy store-unaware rows discarded; next sync is a clean "
                "full upload per store)",
                flush=True,
            )

    # ---- agent configuration ---------------------------------------------

    def set_config(self, key, value):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO agent_configuration (config_key, config_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(config_key) DO UPDATE SET
                    config_value=excluded.config_value, updated_at=CURRENT_TIMESTAMP
                """,
                (key, None if value is None else str(value)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_config(self, key, default=None):
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT config_value FROM agent_configuration WHERE config_key=?",
                (key,),
            )
            row = cur.fetchone()
            return row[0] if row else default
        finally:
            conn.close()

    # ---- downloaded sync configuration (028B) -----------------------------

    def save_sync_config(self, tables):
        """Replace local sync_table_config / sync_column_config from the HO
        configuration payload. HO is the single source of truth."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM sync_table_config")
            conn.execute("DELETE FROM sync_column_config")
            for table in tables:
                stid = str(table.get("sync_table_id"))
                conn.execute(
                    """
                    INSERT INTO sync_table_config
                    (sync_table_id, table_name, sync_mode, watermark_column,
                     window_days, window_months, custom_where, sync_order, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (stid, table.get("table_name"), table.get("sync_mode"),
                     table.get("watermark_column"), table.get("window_days"),
                     table.get("window_months"), table.get("custom_where"),
                     table.get("sync_order")),
                )
                for col in table.get("columns", []):
                    conn.execute(
                        """
                        INSERT INTO sync_column_config
                        (sync_table_id, table_name, column_name, data_type,
                         is_selected, is_pk, is_hash, is_watermark, column_order)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (stid, table.get("table_name"), col.get("column_name"),
                         col.get("data_type"), int(bool(col.get("is_selected"))),
                         int(bool(col.get("is_pk"))), int(bool(col.get("is_hash"))),
                         int(bool(col.get("is_watermark"))), col.get("column_order")),
                    )
            conn.commit()
        finally:
            conn.close()

    def table_config_count(self):
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM sync_table_config").fetchone()[0]
        finally:
            conn.close()

    # ---- schema catalog delta (028C) --------------------------------------

    def get_catalog_hashes(self):
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT schema_name||'.'||table_name||'.'||column_name, catalog_hash "
                "FROM schema_catalog"
            )
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()

    def upsert_catalog(self, entries):
        if not entries:
            return
        conn = self._connect()
        try:
            conn.executemany(
                """
                INSERT INTO schema_catalog
                (schema_name, table_name, column_name, data_type, max_length,
                 precision_value, scale_value, is_nullable, is_identity,
                 is_primary_key, catalog_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(schema_name, table_name, column_name) DO UPDATE SET
                    data_type=excluded.data_type, max_length=excluded.max_length,
                    precision_value=excluded.precision_value,
                    scale_value=excluded.scale_value, is_nullable=excluded.is_nullable,
                    is_identity=excluded.is_identity,
                    is_primary_key=excluded.is_primary_key,
                    catalog_hash=excluded.catalog_hash
                """,
                entries,
            )
            conn.commit()
        finally:
            conn.close()

    # ---- execution / ack history (029E) -----------------------------------

    def record_execution(self, execution_id, status, completed=False):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sync_execution (execution_id, status, completed_at)
                VALUES (?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
                ON CONFLICT(execution_id) DO UPDATE SET
                    status=excluded.status,
                    completed_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE completed_at END
                """,
                (execution_id, status, completed, completed),
            )
            conn.commit()
        finally:
            conn.close()

    def record_ack(self, chunk_execution_id, execution_id, table_name, chunk_no):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO sync_ack
                (chunk_execution_id, execution_id, table_name, chunk_no, acked_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (chunk_execution_id, execution_id, table_name, chunk_no),
            )
            conn.commit()
        finally:
            conn.close()

    # ---- row hash cache (master tables) -----------------------------------

    def get_row_hashes(self, table_name):
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT source_pk, row_hash FROM sync_row_cache "
                "WHERE store_id=? AND table_name=?",
                (self.store_id, table_name),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()

    def upsert_row_hashes(self, table_name, pk_hash_pairs):
        if not pk_hash_pairs:
            return
        conn = self._connect()
        try:
            conn.executemany(
                """
                INSERT INTO sync_row_cache
                    (store_id, table_name, source_pk, row_hash, last_sync_time)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(store_id, table_name, source_pk) DO UPDATE SET
                    row_hash=excluded.row_hash,
                    last_sync_time=CURRENT_TIMESTAMP
                """,
                [(self.store_id, table_name, pk, h) for pk, h in pk_hash_pairs],
            )
            conn.commit()
        finally:
            conn.close()

    def delete_row_hashes(self, table_name, pks):
        if not pks:
            return
        conn = self._connect()
        try:
            conn.executemany(
                "DELETE FROM sync_row_cache "
                "WHERE store_id=? AND table_name=? AND source_pk=?",
                [(self.store_id, table_name, pk) for pk in pks],
            )
            conn.commit()
        finally:
            conn.close()

    def row_cache_count(self, table_name):
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sync_row_cache "
                "WHERE store_id=? AND table_name=?",
                (self.store_id, table_name),
            )
            return cur.fetchone()[0]
        finally:
            conn.close()

    # ---- table state / watermark (transaction tables) ---------------------

    def get_table_state(self, table_name):
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT last_full_sync, last_incremental_sync, last_watermark
                FROM sync_table_state WHERE store_id=? AND table_name=?
                """,
                (self.store_id, table_name),
            )
            row = cur.fetchone()
            if not row:
                return {"last_full_sync": None, "last_incremental_sync": None,
                        "last_watermark": None}
            return {"last_full_sync": row[0], "last_incremental_sync": row[1],
                    "last_watermark": row[2]}
        finally:
            conn.close()

    def get_last_watermark(self, table_name):
        return self.get_table_state(table_name)["last_watermark"]

    def set_last_watermark(self, table_name, value):
        self._upsert_state(table_name, last_watermark=str(value) if value is not None else None,
                           last_incremental_sync=_now())

    def mark_full_sync(self, table_name):
        self._upsert_state(table_name, last_full_sync=_now())

    def _upsert_state(self, table_name, **fields):
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT 1 FROM sync_table_state WHERE store_id=? AND table_name=?",
                (self.store_id, table_name),
            )
            exists = cur.fetchone() is not None
            if exists:
                sets = ", ".join(f"{k}=?" for k in fields)
                conn.execute(
                    f"UPDATE sync_table_state SET {sets} "
                    "WHERE store_id=? AND table_name=?",
                    (*fields.values(), self.store_id, table_name),
                )
            else:
                cols = ", ".join(["store_id", "table_name", *fields.keys()])
                qs = ", ".join(["?"] * (len(fields) + 2))
                conn.execute(
                    f"INSERT INTO sync_table_state ({cols}) VALUES ({qs})",
                    (self.store_id, table_name, *fields.values()),
                )
            conn.commit()
        finally:
            conn.close()

    # back-compat (V1 callers)
    def get_watermark(self, table_name):
        return self.get_last_watermark(table_name)

    def set_watermark(self, table_name, value):
        self.set_last_watermark(table_name, value)

    # ---- pending chunk outbox (offline-HO recovery) -----------------------

    def queue_chunk(self, execution_id, table_name, chunk_no, payload,
                    total_rows, sync_type):
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO sync_pending_chunks
                (execution_id, table_name, chunk_no, payload, total_rows, sync_type, status)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (execution_id, table_name, chunk_no, json.dumps(payload),
                 total_rows, sync_type),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_pending_chunks(self):
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT chunk_id, execution_id, table_name, chunk_no, payload,
                       total_rows, sync_type
                FROM sync_pending_chunks WHERE status='PENDING'
                ORDER BY chunk_id
                """
            )
            return [
                {
                    "chunk_id": r[0], "execution_id": r[1], "table_name": r[2],
                    "chunk_no": r[3], "payload": json.loads(r[4]),
                    "total_rows": r[5], "sync_type": r[6],
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def mark_chunk_done(self, chunk_id):
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM sync_pending_chunks WHERE chunk_id=?", (chunk_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def pending_chunk_count(self):
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sync_pending_chunks WHERE status='PENDING'"
            )
            return cur.fetchone()[0]
        finally:
            conn.close()

    # ---- execution log ----------------------------------------------------

    def log_execution(self, execution_id, table_name, examined, changed,
                      uploaded, skipped):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sync_execution_log
                (execution_id, table_name, rows_examined, rows_changed,
                 rows_uploaded, rows_skipped)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id, table_name) DO UPDATE SET
                    rows_examined=excluded.rows_examined,
                    rows_changed=excluded.rows_changed,
                    rows_uploaded=excluded.rows_uploaded,
                    rows_skipped=excluded.rows_skipped
                """,
                (execution_id, table_name, examined, changed, uploaded, skipped),
            )
            conn.commit()
        finally:
            conn.close()

    def cache_size_bytes(self):
        try:
            return Path(self.db_path).stat().st_size
        except OSError:
            return 0


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")
