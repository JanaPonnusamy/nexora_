"""
Sync Administration data access.

ARCHITECTURE NOTE
-----------------
Heartbeat = Agent Health ONLY. The Store Agent (Windows service) polls HO every
~30 seconds and writes to dbo.store_agent_registry / dbo.agent_heartbeat_log.
The heartbeat NEVER opens the store database -- it does not read GRN, Bills,
Sales, Purchases or any business table.

Sync = Business Data. The store database is READ-ONLY and is connected only
during an active sync execution; there is no persistent connection.

Therefore store online/offline + activity is derived ONLY from
store_agent_registry + agent_heartbeat_log + sync_execution -- never from store
business tables.
"""

from config.database import get_connection

def _iso(value):
    return value.isoformat() if value else None


class SyncAdminRepository:

    # ===== Control Center (read-only) =====

    def control_center(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM dbo.stores WHERE is_active = 1")
        total = cur.fetchone()[0]
        # Online = agent heartbeat seen within the last 90s (30s poll, allow 3 misses).
        cur.execute("""
        SELECT COUNT(*) FROM dbo.stores s
        WHERE s.is_active = 1 AND EXISTS (
            SELECT 1 FROM dbo.store_agent_registry reg
            WHERE reg.store_id = s.store_id AND reg.is_active = 1
              AND reg.last_heartbeat >= DATEADD(SECOND, -90, GETDATE())
        )
        """)
        online = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution WHERE execution_status = 'RUNNING'")
        running = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution WHERE execution_status = 'QUEUED'")
        queued = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution_history WHERE status = 'COMPLETED' AND CAST(started_at AS DATE) = CAST(GETDATE() AS DATE)")
        completed_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution_history WHERE status = 'FAILED' AND CAST(started_at AS DATE) = CAST(GETDATE() AS DATE)")
        failed_today = cur.fetchone()[0]

        kpis = {
            "stores_online": online,
            "stores_offline": total - online,
            "sync_running": running,
            "queued": queued,
            "completed_today": completed_today,
            "failed_today": failed_today,
        }

        cur.execute("""
        SELECT s.store_id, s.store_code, s.store_name,
            reg.connection_type,
            CASE WHEN reg.last_heartbeat >= DATEADD(SECOND, -90, GETDATE()) THEN 'Online' ELSE 'Offline' END AS agent_status,
            (SELECT MAX(h.completed_at) FROM dbo.sync_execution_history h WHERE h.store_id = s.store_id) AS last_sync,
            (SELECT COUNT(*) FROM dbo.sync_execution e WHERE e.store_id = s.store_id AND e.execution_status = 'RUNNING') AS running
        FROM dbo.stores s
        LEFT JOIN dbo.store_agent_registry reg ON reg.store_id = s.store_id AND reg.is_active = 1
        WHERE s.is_active = 1
        ORDER BY s.store_code
        """)
        stores = []
        for r in cur.fetchall():
            is_running = (r[6] or 0) > 0
            stores.append({
                "store_id": str(r[0]),
                "store_code": r[1],
                "store_name": r[2],
                "connection_type": r[3] or "Offline",
                "agent_status": r[4],
                "last_sync": _iso(r[5]),
                "current_activity": "Syncing" if is_running else "Idle",
                "is_syncing": is_running,
                "status": "Syncing" if is_running else r[4],
            })

        conn.close()
        return {"kpis": kpis, "stores": stores}

    # ===== Schedules (CRUD + suspend) =====

    _schema_ready = False

    def ensure_schema(self, cur):
        """Idempotently add the columns the schedule screen needs. Safe to run
        on every process; COL_LENGTH checks are cheap and the ALTERs only fire
        when a column is genuinely missing."""
        if SyncAdminRepository._schema_ready:
            return
        for stmt in (
            "IF COL_LENGTH('dbo.sync_schedule','store_id') IS NULL "
            "ALTER TABLE dbo.sync_schedule ADD store_id UNIQUEIDENTIFIER NULL",
            "IF COL_LENGTH('dbo.sync_schedule','sync_mode') IS NULL "
            "ALTER TABLE dbo.sync_schedule ADD sync_mode VARCHAR(20) NOT NULL "
            "CONSTRAINT DF_sync_schedule_sync_mode DEFAULT 'FULL'",
            "IF COL_LENGTH('dbo.sync_schedule','suspended_until') IS NULL "
            "ALTER TABLE dbo.sync_schedule ADD suspended_until DATETIME NULL",
            "IF COL_LENGTH('dbo.sync_schedule','last_run_at') IS NULL "
            "ALTER TABLE dbo.sync_schedule ADD last_run_at DATETIME NULL",
            "IF COL_LENGTH('dbo.sync_schedule','updated_at') IS NULL "
            "ALTER TABLE dbo.sync_schedule ADD updated_at DATETIME NULL",
        ):
            cur.execute(stmt)
        SyncAdminRepository._schema_ready = True

    @staticmethod
    def _status(is_enabled, suspended_until):
        import datetime as _dt
        if suspended_until and suspended_until > _dt.datetime.now():
            return "Suspended"
        return "Active" if is_enabled else "Disabled"

    def _serialize_schedule(self, r):
        return {
            "schedule_id": r[0],
            "tenant_id": str(r[1]) if r[1] else None,
            "store_id": str(r[2]) if r[2] else None,
            "store_code": r[3],
            "store_name": r[4],
            "schedule_name": r[5],
            "schedule_type": r[6],
            "start_time": _iso(r[7]),
            "sync_mode": r[8],
            "is_enabled": bool(r[9]),
            "suspended_until": _iso(r[10]),
            "last_run_at": _iso(r[11]),
            "created_at": _iso(r[12]),
            "status": self._status(bool(r[9]), r[10]),
        }

    _SELECT = """
        SELECT sc.schedule_id, sc.tenant_id, sc.store_id, st.store_code, st.store_name,
               sc.schedule_name, sc.schedule_type, sc.start_time, sc.sync_mode,
               sc.is_enabled, sc.suspended_until, sc.last_run_at, sc.created_at
        FROM dbo.sync_schedule sc
        LEFT JOIN dbo.stores st ON st.store_id = sc.store_id
    """

    def get_schedules(self):
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        cur.execute(self._SELECT + " ORDER BY sc.start_time, sc.schedule_name")
        rows = [self._serialize_schedule(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_schedule(self, schedule_id):
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        cur.execute(self._SELECT + " WHERE sc.schedule_id = ?", schedule_id)
        row = cur.fetchone()
        conn.close()
        return self._serialize_schedule(row) if row else None

    def _resolve_tenant(self, cur, store_id, tenant_id):
        if store_id:
            cur.execute("SELECT tenant_id FROM dbo.stores WHERE store_id = ?", store_id)
            row = cur.fetchone()
            if row:
                return row[0]
        if tenant_id:
            return tenant_id
        cur.execute("SELECT TOP 1 tenant_id FROM dbo.tenants ORDER BY tenant_name")
        row = cur.fetchone()
        return row[0] if row else None

    def create_schedule(self, schedule_name, schedule_type, store_id, start_time,
                        sync_mode, is_enabled, tenant_id=None):
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        tenant = self._resolve_tenant(cur, store_id, tenant_id)
        cur.execute("""
        INSERT INTO dbo.sync_schedule
            (tenant_id, store_id, schedule_name, schedule_type, start_time,
             sync_mode, is_enabled, created_at, updated_at)
        OUTPUT INSERTED.schedule_id
        VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
        """, tenant, store_id, schedule_name, schedule_type, start_time,
             sync_mode, 1 if is_enabled else 0)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update_schedule(self, schedule_id, schedule_name, schedule_type, store_id,
                        start_time, sync_mode, is_enabled):
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        cur.execute("""
        UPDATE dbo.sync_schedule
        SET schedule_name = ?, schedule_type = ?, store_id = ?, start_time = ?,
            sync_mode = ?, is_enabled = ?, updated_at = GETDATE()
        WHERE schedule_id = ?
        """, schedule_name, schedule_type, store_id, start_time, sync_mode,
             1 if is_enabled else 0, schedule_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_schedule_status(self, schedule_id, is_enabled):
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        cur.execute("UPDATE dbo.sync_schedule SET is_enabled = ?, updated_at = GETDATE() "
                    "WHERE schedule_id = ?", 1 if is_enabled else 0, schedule_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def suspend_schedule(self, schedule_id, suspended_until):
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        cur.execute("UPDATE dbo.sync_schedule SET suspended_until = ?, updated_at = GETDATE() "
                    "WHERE schedule_id = ?", suspended_until, schedule_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def delete_schedule(self, schedule_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.sync_schedule WHERE schedule_id = ?", schedule_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def seed_default_schedules(self):
        """Per-store daily schedules: a morning run staggered 06:15-06:25 (2 min
        apart) plus an afternoon run at 13:00 (staggered). Idempotent by name."""
        import datetime as _dt
        conn = get_connection()
        cur = conn.cursor()
        self.ensure_schema(cur)
        cur.execute("SELECT store_id, store_code, tenant_id FROM dbo.stores "
                    "WHERE is_active = 1 ORDER BY store_code")
        stores = cur.fetchall()
        created = 0
        for idx, (store_id, code, tenant_id) in enumerate(stores):
            morning = _dt.datetime(2000, 1, 1, 6, 15) + _dt.timedelta(minutes=2 * idx)
            afternoon = _dt.datetime(2000, 1, 1, 13, 0) + _dt.timedelta(minutes=2 * idx)
            for name, when in ((f"{code} Morning Sync", morning),
                               (f"{code} Afternoon Sync", afternoon)):
                cur.execute("SELECT COUNT(*) FROM dbo.sync_schedule WHERE schedule_name = ?", name)
                if cur.fetchone()[0] == 0:
                    cur.execute("""
                    INSERT INTO dbo.sync_schedule
                        (tenant_id, store_id, schedule_name, schedule_type, start_time,
                         sync_mode, is_enabled, created_at, updated_at)
                    VALUES (?, ?, ?, 'DAILY', ?, 'FULL', 1, GETDATE(), GETDATE())
                    """, tenant_id, store_id, name, when)
                    created += 1
        conn.commit()
        conn.close()
        return {"created": created, "stores": len(stores)}

    # ===== Store Health (read-only) =====

    def store_health(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT s.store_id, s.store_code, s.store_name,
            reg.connection_type,
            reg.last_heartbeat,
            CASE WHEN reg.last_heartbeat >= DATEADD(SECOND, -90, GETDATE()) THEN 'Online' ELSE 'Offline' END AS agent_status,
            (SELECT MAX(h.completed_at) FROM dbo.sync_execution_history h WHERE h.store_id = s.store_id) AS last_sync,
            (SELECT COUNT(*) FROM dbo.sync_execution e WHERE e.store_id = s.store_id AND e.execution_status IN ('QUEUED','RUNNING')) AS pending_queue
        FROM dbo.stores s
        LEFT JOIN dbo.store_agent_registry reg ON reg.store_id = s.store_id AND reg.is_active = 1
        WHERE s.is_active = 1
        ORDER BY s.store_code
        """)
        rows = [{
            "store_id": str(r[0]),
            "store_code": r[1],
            "store_name": r[2],
            "connection_type": r[3] or "Offline",
            "last_heartbeat": _iso(r[4]),
            "agent_status": r[5],
            "last_sync": _iso(r[6]),
            "pending_queue": r[7] or 0,
        } for r in cur.fetchall()]
        conn.close()
        return rows

    # ===== Sync History (read-only) =====

    def get_history(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT TOP 200 h.sync_id, h.store_id, h.sync_mode, h.started_at, h.completed_at,
            h.duration_seconds, h.processed_rows, h.status,
            st.store_code, st.store_name
        FROM dbo.sync_execution_history h
        LEFT JOIN dbo.stores st ON st.store_id = h.store_id
        ORDER BY h.started_at DESC
        """)
        rows = [{
            "sync_id": r[0],
            "store_id": str(r[1]) if r[1] else None,
            "store_code": r[8],
            "store_name": r[9],
            "scope": r[2],
            "started_at": _iso(r[3]),
            "completed_at": _iso(r[4]),
            "duration_seconds": r[5],
            "rows": r[6] or 0,
            "status": r[7],
        } for r in cur.fetchall()]
        conn.close()
        return rows

    def get_history_details(self, sync_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT table_name, chunk_no, rows_processed, rows_failed, duration_seconds, status, error_message
        FROM dbo.sync_execution_details
        WHERE sync_id = ?
        ORDER BY table_name, chunk_no
        """, sync_id)
        rows = [{
            "table_name": r[0],
            "chunk_no": r[1],
            "rows_processed": r[2] or 0,
            "rows_failed": r[3] or 0,
            "duration_seconds": r[4],
            "status": r[5],
            "error_message": r[6],
        } for r in cur.fetchall()]
        conn.close()
        return rows

    # ===== Table Configuration (CRUD) =====

    def catalog_tables(self, search=None):
        conn = get_connection()
        cur = conn.cursor()
        if search:
            cur.execute("""
            SELECT DISTINCT schema_name, table_name
            FROM sync.sync_schema_catalog
            WHERE is_active = 1 AND table_name LIKE ?
            ORDER BY table_name
            """, f"%{search}%")
        else:
            cur.execute("""
            SELECT DISTINCT schema_name, table_name
            FROM sync.sync_schema_catalog
            WHERE is_active = 1
            ORDER BY table_name
            """)
        rows = [{"schema_name": r[0], "table_name": r[1]} for r in cur.fetchall()]
        conn.close()
        return rows

    def get_tables(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT sync_table_id, table_name, is_active, sync_mode, watermark_column, window_days, custom_where, sync_order
        FROM sync.sync_table_master
        ORDER BY sync_order, table_name
        """)
        rows = [self._serialize_table(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def available_tables(self, search=None):
        """Every discovered catalog table left-joined to its configured state,
        so the Table Configuration tab can search the full source schema and
        enable tables that are not yet in the master."""
        conn = get_connection()
        cur = conn.cursor()
        sql = """
        SELECT c.schema_name, c.table_name,
               m.sync_table_id, m.is_active, m.sync_mode
        FROM (
            SELECT DISTINCT schema_name, table_name
            FROM sync.sync_schema_catalog
            WHERE is_active = 1
        ) c
        LEFT JOIN sync.sync_table_master m
               ON m.table_name = c.table_name
        {where}
        ORDER BY c.table_name
        """
        if search:
            cur.execute(sql.format(where="WHERE c.table_name LIKE ?"), f"%{search}%")
        else:
            cur.execute(sql.format(where=""))
        rows = [
            {
                "schema_name": r[0],
                "table_name": r[1],
                "sync_table_id": str(r[2]) if r[2] is not None else None,
                "is_configured": r[2] is not None,
                "is_active": bool(r[3]) if r[3] is not None else False,
                "sync_mode": r[4],
            }
            for r in cur.fetchall()
        ]
        conn.close()
        return rows

    def get_table_by_id(self, sync_table_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT sync_table_id, table_name, is_active, sync_mode, watermark_column, window_days, custom_where, sync_order
        FROM sync.sync_table_master
        WHERE sync_table_id = ?
        """, sync_table_id)
        row = cur.fetchone()
        conn.close()
        return self._serialize_table(row) if row else None

    def table_name_exists(self, table_name, exclude_id=None):
        conn = get_connection()
        cur = conn.cursor()
        if exclude_id:
            cur.execute("SELECT COUNT(*) FROM sync.sync_table_master WHERE table_name = ? AND sync_table_id <> ?", table_name, exclude_id)
        else:
            cur.execute("SELECT COUNT(*) FROM sync.sync_table_master WHERE table_name = ?", table_name)
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def create_table(self, table_name, sync_mode, watermark_column, window_days, custom_where, sync_order, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO sync.sync_table_master
            (sync_table_id, table_name, is_active, sync_mode, watermark_column, window_days, custom_where, sync_order, created_at)
        OUTPUT INSERTED.sync_table_id
        VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, table_name, 1 if is_active else 0, sync_mode, watermark_column, window_days, custom_where, sync_order)
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    def update_table(self, sync_table_id, table_name, sync_mode, watermark_column, window_days, custom_where, sync_order):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE sync.sync_table_master
        SET table_name = ?, sync_mode = ?, watermark_column = ?, window_days = ?, custom_where = ?, sync_order = ?
        WHERE sync_table_id = ?
        """, table_name, sync_mode, watermark_column, window_days, custom_where, sync_order, sync_table_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    def set_table_active(self, sync_table_id, is_active):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE sync.sync_table_master SET is_active = ? WHERE sync_table_id = ?", 1 if is_active else 0, sync_table_id)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    @staticmethod
    def _serialize_table(r):
        return {
            "sync_table_id": str(r[0]),
            "table_name": r[1],
            "is_active": bool(r[2]),
            "sync_mode": r[3],
            "watermark_column": r[4],
            "window_days": r[5],
            "custom_where": r[6],
            "sync_order": r[7],
        }

    # ===== Column Mapping (CRUD) =====

    def get_table_columns(self, sync_table_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM sync.sync_table_master WHERE sync_table_id = ?", sync_table_id)
        row = cur.fetchone()
        if not row:
            conn.close()
            return None
        table_name = row[0]

        cur.execute("""
        SELECT c.column_name, c.data_type, c.ordinal_position, c.is_primary_key,
            m.mapping_id, m.is_selected, m.is_pk, m.is_hash, m.is_watermark
        FROM sync.sync_schema_catalog c
        LEFT JOIN sync.sync_column_mapping m
            ON m.sync_table_id = ? AND m.column_name = c.column_name
        WHERE c.table_name = ? AND c.is_active = 1
        ORDER BY c.ordinal_position
        """, sync_table_id, table_name)

        columns = []
        for r in cur.fetchall():
            has_mapping = r[4] is not None
            columns.append({
                "column_name": r[0],
                "data_type": r[1],
                "column_order": r[2],
                "catalog_is_pk": bool(r[3]),
                "is_selected": bool(r[5]) if has_mapping else False,
                "is_pk": bool(r[6]) if has_mapping else bool(r[3]),
                "is_hash": bool(r[7]) if has_mapping else False,
                "is_watermark": bool(r[8]) if has_mapping else False,
            })
        conn.close()
        return {"table_name": table_name, "columns": columns}

    def upsert_mapping(self, sync_table_id, table_name, column_name, data_type,
                       is_selected, is_pk, is_hash, is_watermark, column_order):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM sync.sync_column_mapping WHERE sync_table_id = ? AND column_name = ?",
            sync_table_id, column_name
        )
        exists = cur.fetchone()[0] > 0
        if exists:
            cur.execute("""
            UPDATE sync.sync_column_mapping
            SET data_type = ?, is_selected = ?, is_pk = ?, is_hash = ?, is_watermark = ?, column_order = ?
            WHERE sync_table_id = ? AND column_name = ?
            """, data_type, int(is_selected), int(is_pk), int(is_hash), int(is_watermark), column_order,
                 sync_table_id, column_name)
        else:
            cur.execute("""
            INSERT INTO sync.sync_column_mapping
                (mapping_id, sync_table_id, table_name, column_name, data_type, is_selected, is_pk, is_hash, is_watermark, column_order, created_at)
            VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, sync_table_id, table_name, column_name, data_type,
                 int(is_selected), int(is_pk), int(is_hash), int(is_watermark), column_order)
        conn.commit()
        conn.close()
