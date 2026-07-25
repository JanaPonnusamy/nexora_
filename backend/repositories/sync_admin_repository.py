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

    def _reap_stale_executions(self, cur):
        """Fail-close orphaned RUNNING executions.

        The Store Agent is the only writer that can move an execution out of
        RUNNING (complete_task/fail_task in modules/sync/runtime_repository.py).
        If the agent process dies or the service restarts mid-sync, nothing
        ever calls those, so the row stays RUNNING forever and the dashboard
        shows a permanently "stuck" job even after later syncs for the same
        store complete fine. Two independent signals catch this:
          1. The agent heartbeat (dbo.store_agent_registry) is written
             independently of any in-progress sync, so an agent gone silent
             for 90s+ while an execution is still RUNNING means the agent
             itself died mid-sync.
          2. A Store Agent service restart can come back up and resume
             heartbeating fine while the specific in-flight execution it lost
             track of never gets revisited (heartbeat alone misses this case
             -- confirmed against a real stuck row whose agent was ONLINE the
             whole time). The slowest table/full sync observed in history is
             ~5 minutes, so any RUNNING execution older than 2 hours is safe
             to treat as orphaned regardless of agent health.
        """
        cur.execute("""
            UPDATE e
            SET e.execution_status = 'FAILED', e.completed_at = GETDATE()
            FROM dbo.sync_execution e
            LEFT JOIN dbo.store_agent_registry reg
                ON reg.store_id = e.store_id AND reg.is_active = 1
            WHERE e.execution_status = 'RUNNING'
              AND (reg.last_heartbeat IS NULL
                   OR reg.last_heartbeat < DATEADD(SECOND, -90, GETDATE())
                   OR e.started_at < DATEADD(HOUR, -2, GETDATE()))
        """)
        if cur.rowcount:
            cur.execute("""
                INSERT INTO dbo.sync_execution_audit (execution_id, action_name, message)
                SELECT e.execution_id, 'FAILED', 'Marked failed: execution orphaned (agent offline or stuck past max runtime)'
                FROM dbo.sync_execution e
                WHERE e.execution_status = 'FAILED' AND e.completed_at >= DATEADD(SECOND, -5, GETDATE())
            """)
        cur.connection.commit()

    def control_center(self):
        conn = get_connection()
        cur = conn.cursor()
        self._reap_stale_executions(cur)

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
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution WHERE execution_status IN ('QUEUED','PENDING')")
        queued = cur.fetchone()[0]
        # History/KPIs come from the live runtime table dbo.sync_execution (the
        # legacy dbo.sync_execution_history is never populated by the engine).
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution WHERE execution_status = 'COMPLETED' AND CAST(started_at AS DATE) = CAST(GETDATE() AS DATE)")
        completed_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dbo.sync_execution WHERE execution_status = 'FAILED' AND CAST(started_at AS DATE) = CAST(GETDATE() AS DATE)")
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
            (SELECT MAX(h.completed_at) FROM dbo.sync_execution h WHERE h.store_id = s.store_id AND h.execution_status = 'COMPLETED') AS last_sync,
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
            (SELECT MAX(h.completed_at) FROM dbo.sync_execution h WHERE h.store_id = s.store_id AND h.execution_status = 'COMPLETED') AS last_sync,
            (SELECT COUNT(*) FROM dbo.sync_execution e WHERE e.store_id = s.store_id AND e.execution_status IN ('QUEUED','PENDING','RUNNING')) AS pending_queue
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
    #
    # ROOT CAUSE FIX: the sync engine (modules/sync/runtime_repository.py) writes
    # every execution to dbo.sync_execution + dbo.sync_execution_details (per-table
    # summary rows at chunk_no = 0) + dbo.sync_chunk_execution (per-chunk). The
    # legacy dbo.sync_execution_history table is NEVER written, so reading it made
    # History permanently empty. All history reads now target the live tables.

    def get_history(self, store_id=None, status=None, execution_type=None,
                    sync_mode=None, search=None, limit=200):
        conn = get_connection()
        cur = conn.cursor()
        self._reap_stale_executions(cur)
        where, params = [], []
        if store_id:
            where.append("e.store_id = ?"); params.append(store_id)
        if status:
            where.append("e.execution_status = ?"); params.append(status)
        if execution_type:
            where.append("e.execution_type = ?"); params.append(execution_type)
        if sync_mode:
            where.append("e.sync_mode = ?"); params.append(sync_mode)
        if search:
            where.append("CAST(e.execution_id AS varchar(50)) LIKE ?")
            params.append(f"%{search}%")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        cur.execute(f"""
        SELECT TOP (?) e.execution_id, e.store_id, e.execution_type, e.sync_mode,
            e.execution_status, e.started_at, e.completed_at,
            DATEDIFF(SECOND, e.started_at, ISNULL(e.completed_at, GETDATE())) AS duration_seconds,
            st.store_code, st.store_name,
            COALESCE(e.initiated_by, e.created_by) AS triggered_by,
            d.tbl_count, d.rows_read, d.rows_uploaded, d.rows_inserted, d.rows_updated,
            ck.err_count, ck.retry_count,
            (SELECT TOP 1 r.agent_version FROM dbo.store_agent_registry r
             WHERE r.store_id = e.store_id AND r.is_active = 1
             ORDER BY r.last_heartbeat DESC) AS agent_version
        FROM dbo.sync_execution e
        LEFT JOIN dbo.stores st ON st.store_id = e.store_id
        OUTER APPLY (
            SELECT COUNT(DISTINCT d.table_name) AS tbl_count,
                   SUM(ISNULL(d.rows_examined, d.rows_processed)) AS rows_read,
                   SUM(ISNULL(d.rows_uploaded, d.rows_processed)) AS rows_uploaded,
                   SUM(ISNULL(d.rows_inserted, 0)) AS rows_inserted,
                   SUM(ISNULL(d.rows_updated, 0)) AS rows_updated
            FROM dbo.sync_execution_details d
            WHERE d.execution_id = e.execution_id AND d.chunk_no = 0
        ) d
        OUTER APPLY (
            SELECT SUM(CASE WHEN c.chunk_status = 'FAILED' THEN 1 ELSE 0 END) AS err_count,
                   SUM(ISNULL(c.retry_count, 0)) AS retry_count
            FROM dbo.sync_chunk_execution c
            WHERE c.execution_id = e.execution_id
        ) ck
        {clause}
        ORDER BY e.started_at DESC
        """, [limit] + params)
        rows = [{
            "execution_id": str(r[0]),
            "sync_id": str(r[0]),  # legacy alias for existing callers
            "store_id": str(r[1]) if r[1] else None,
            "execution_type": r[2],
            "scope": r[3],
            "sync_mode": r[3],
            "status": r[4],
            "started_at": _iso(r[5]),
            "completed_at": _iso(r[6]),
            "duration_seconds": r[7],
            "store_code": r[8],
            "store_name": r[9],
            "triggered_by": str(r[10]) if r[10] else None,
            "table_count": r[11] or 0,
            "rows": int(r[12]) if r[12] else 0,
            "rows_read": int(r[12]) if r[12] else 0,
            "rows_uploaded": int(r[13]) if r[13] else 0,
            "rows_inserted": int(r[14]) if r[14] else 0,
            "rows_updated": int(r[15]) if r[15] else 0,
            "rows_deleted": 0,  # engine performs upsert-only (no delete propagation)
            "error_count": int(r[16]) if r[16] else 0,
            "warning_count": 0,
            "retry_count": int(r[17]) if r[17] else 0,
            "agent_version": r[18],
        } for r in cur.fetchall()]
        conn.close()
        return rows

    def get_execution_summary(self, execution_id):
        """Header + derived timeline stages for one execution."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT e.execution_id, e.tenant_id, e.store_id, e.execution_type,
            e.sync_mode, e.execution_status, e.started_at, e.completed_at,
            DATEDIFF(SECOND, e.started_at, ISNULL(e.completed_at, GETDATE())),
            e.total_tables, e.completed_tables, e.failed_tables,
            COALESCE(e.initiated_by, e.created_by),
            st.store_code, st.store_name,
            (SELECT TOP 1 r.agent_version FROM dbo.store_agent_registry r
             WHERE r.store_id = e.store_id AND r.is_active = 1
             ORDER BY r.last_heartbeat DESC),
            (SELECT MAX(t.tenant_name) FROM dbo.tenants t WHERE t.tenant_id = e.tenant_id)
        FROM dbo.sync_execution e
        LEFT JOIN dbo.stores st ON st.store_id = e.store_id
        WHERE e.execution_id = ?
        """, execution_id)
        r = cur.fetchone()
        if not r:
            conn.close()
            return None

        # Roll-up metrics from the per-table summary rows (chunk_no = 0).
        cur.execute("""
        SELECT COUNT(DISTINCT table_name),
               SUM(ISNULL(rows_examined, rows_processed)),
               SUM(ISNULL(rows_uploaded, rows_processed)),
               SUM(ISNULL(rows_inserted, 0)), SUM(ISNULL(rows_updated, 0)),
               SUM(ISNULL(rows_skipped, 0))
        FROM dbo.sync_execution_details
        WHERE execution_id = ? AND chunk_no = 0
        """, execution_id)
        m = cur.fetchone()

        # Timeline: real timestamps we actually record. Chunk activity brackets
        # the upload window; fall back to the per-table detail rows when an
        # execution has no chunk records (older / re-sync runs).
        cur.execute("""
        SELECT MIN(started_at), MAX(completed_at),
               SUM(CASE WHEN chunk_status = 'FAILED' THEN 1 ELSE 0 END),
               SUM(ISNULL(retry_count, 0))
        FROM dbo.sync_chunk_execution WHERE execution_id = ?
        """, execution_id)
        ck = cur.fetchone()
        cur.execute("""
        SELECT MIN(started_at), MAX(completed_at)
        FROM dbo.sync_execution_details WHERE execution_id = ? AND chunk_no = 0
        """, execution_id)
        dtl = cur.fetchone()
        conn.close()

        started, completed = r[6], r[7]
        first_activity = ck[0] or dtl[0]
        last_activity = ck[1] or dtl[1]
        timeline = [
            {"stage": "Started", "at": _iso(started)},
            {"stage": "Table Processing", "at": _iso(first_activity)},
            {"stage": "Upload / Merge", "at": _iso(last_activity or completed)},
            {"stage": "Completed", "at": _iso(completed)},
        ]
        return {
            "execution_id": str(r[0]),
            "tenant_id": str(r[1]) if r[1] else None,
            "store_id": str(r[2]) if r[2] else None,
            "execution_type": r[3],
            "sync_mode": r[4],
            "status": r[5],
            "started_at": _iso(started),
            "completed_at": _iso(completed),
            "duration_seconds": r[8],
            "total_tables": r[9],
            "completed_tables": r[10],
            "failed_tables": r[11],
            "triggered_by": str(r[12]) if r[12] else None,
            "store_code": r[13],
            "store_name": r[14],
            "agent_version": r[15],
            "tenant_name": r[16],
            "table_count": m[0] or 0,
            "rows_read": int(m[1]) if m[1] else 0,
            "rows_uploaded": int(m[2]) if m[2] else 0,
            "rows_inserted": int(m[3]) if m[3] else 0,
            "rows_updated": int(m[4]) if m[4] else 0,
            "rows_skipped": int(m[5]) if m[5] else 0,
            "error_count": int(ck[2]) if ck[2] else 0,
            "retry_count": int(ck[3]) if ck[3] else 0,
            "timeline": timeline,
        }

    def get_execution_tables(self, execution_id):
        """Per-table summary rows (chunk_no = 0) for the table execution grid."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT table_name, sync_type, started_at, completed_at,
               DATEDIFF(SECOND, started_at, ISNULL(completed_at, GETDATE())),
               ISNULL(rows_examined, rows_processed), ISNULL(rows_uploaded, rows_processed),
               ISNULL(rows_inserted, 0), ISNULL(rows_updated, 0), ISNULL(rows_skipped, 0),
               status, rows_failed,
               (SELECT COUNT(*) FROM dbo.sync_chunk_execution c
                WHERE c.execution_id = d.execution_id AND c.table_name = d.table_name) AS chunk_count
        FROM dbo.sync_execution_details d
        WHERE execution_id = ? AND chunk_no = 0
        ORDER BY started_at, table_name
        """, execution_id)
        rows = []
        for i, r in enumerate(cur.fetchall(), start=1):
            rows.append({
                "order": i,
                "table_name": r[0],
                "direction": "Store → HO",
                "sync_type": r[1],
                "started_at": _iso(r[2]),
                "completed_at": _iso(r[3]),
                "duration_seconds": r[4],
                "rows_read": int(r[5]) if r[5] else 0,
                "rows_uploaded": int(r[6]) if r[6] else 0,
                "rows_inserted": int(r[7]) if r[7] else 0,
                "rows_updated": int(r[8]) if r[8] else 0,
                "rows_skipped": int(r[9]) if r[9] else 0,
                "status": r[10],
                "rows_failed": int(r[11]) if r[11] else 0,
                "chunk_count": r[12] or 0,
            })
        conn.close()
        return rows

    def get_execution_chunks(self, execution_id, table_name=None):
        conn = get_connection()
        cur = conn.cursor()
        sql = """
        SELECT chunk_execution_id, table_name, chunk_no, chunk_status,
               rows_processed, retry_count, started_at, completed_at,
               DATEDIFF(MILLISECOND, started_at, completed_at), error_message
        FROM dbo.sync_chunk_execution
        WHERE execution_id = ?
        """
        params = [execution_id]
        if table_name:
            sql += " AND table_name = ?"
            params.append(table_name)
        sql += " ORDER BY table_name, chunk_no, chunk_execution_id"
        cur.execute(sql, params)
        rows = [{
            "chunk_execution_id": r[0],
            "table_name": r[1],
            "chunk_no": r[2],
            "status": r[3],
            "rows": int(r[4]) if r[4] else 0,
            "retry_count": r[5] or 0,
            "started_at": _iso(r[6]),
            "completed_at": _iso(r[7]),
            "duration_ms": r[8],
            "error_message": r[9],
        } for r in cur.fetchall()]
        conn.close()
        return rows

    def get_execution_errors(self, execution_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT table_name, chunk_no, retry_count, started_at, completed_at, error_message
        FROM dbo.sync_chunk_execution
        WHERE execution_id = ? AND chunk_status = 'FAILED'
        ORDER BY table_name, chunk_no
        """, execution_id)
        rows = [{
            "table_name": r[0],
            "chunk_no": r[1],
            "retry_count": r[2] or 0,
            "started_at": _iso(r[3]),
            "completed_at": _iso(r[4]),
            "error_message": r[5],
        } for r in cur.fetchall()]
        conn.close()
        return rows

    def get_statistics(self):
        """Performance summary cards for the History header."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN execution_status = 'COMPLETED' THEN 1 ELSE 0 END),
            SUM(CASE WHEN execution_status = 'FAILED' THEN 1 ELSE 0 END),
            SUM(CASE WHEN execution_status = 'RUNNING' THEN 1 ELSE 0 END),
            AVG(CASE WHEN completed_at IS NOT NULL
                     THEN DATEDIFF(SECOND, started_at, completed_at) END)
        FROM dbo.sync_execution
        """)
        s = cur.fetchone()
        cur.execute("""
        SELECT ISNULL(SUM(ISNULL(rows_uploaded, rows_processed)), 0)
        FROM dbo.sync_execution_details
        WHERE chunk_no = 0 AND CAST(created_at AS DATE) = CAST(GETDATE() AS DATE)
        """)
        uploaded_today = cur.fetchone()[0]
        # Largest sync (rows) + slowest table (avg duration) across all history.
        cur.execute("""
        SELECT TOP 1 e.execution_id, SUM(ISNULL(d.rows_uploaded, d.rows_processed)) AS tot
        FROM dbo.sync_execution e
        JOIN dbo.sync_execution_details d
             ON d.execution_id = e.execution_id AND d.chunk_no = 0
        GROUP BY e.execution_id ORDER BY tot DESC
        """)
        largest = cur.fetchone()
        cur.execute("""
        SELECT TOP 1 table_name,
               AVG(DATEDIFF(SECOND, started_at, completed_at)) AS avg_dur
        FROM dbo.sync_execution_details
        WHERE chunk_no = 0 AND completed_at IS NOT NULL AND started_at IS NOT NULL
        GROUP BY table_name ORDER BY avg_dur DESC
        """)
        slowest = cur.fetchone()
        conn.close()

        total = s[0] or 0
        completed = s[1] or 0
        avg_dur = int(s[4]) if s[4] else None
        return {
            "total_executions": total,
            "successful": completed,
            "failed": s[2] or 0,
            "running": s[3] or 0,
            "success_rate": round(completed / total * 100, 1) if total else 0.0,
            "avg_duration_seconds": avg_dur,
            "rows_uploaded_today": int(uploaded_today or 0),
            "largest_sync_rows": int(largest[1]) if largest and largest[1] else 0,
            "largest_sync_id": str(largest[0]) if largest else None,
            "slowest_table": slowest[0] if slowest else None,
            "slowest_table_seconds": int(slowest[1]) if slowest and slowest[1] else None,
        }

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
