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

    # ===== Schedules (read-only) =====

    def get_schedules(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT schedule_id, schedule_name, schedule_type, start_time, is_enabled
        FROM dbo.sync_schedule
        ORDER BY schedule_name
        """)
        rows = [{
            "schedule_id": r[0],
            "schedule_name": r[1],
            "schedule_type": r[2],
            "start_time": _iso(r[3]),
            "is_enabled": bool(r[4]),
        } for r in cur.fetchall()]
        conn.close()
        return rows

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
