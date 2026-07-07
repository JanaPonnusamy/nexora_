import pyodbc

from config.database import get_connection
from modules.sync import type_normalizer
from modules.sync import schema_evolution


def _audit(cursor, execution_id, action_name, message=None):
    cursor.execute(
        """
        INSERT INTO dbo.sync_execution_audit
        (execution_id, action_name, message)
        VALUES (?, ?, ?)
        """,
        (execution_id, action_name, message)
    )


def create_task(tenant_id, store_id, execution_type, sync_mode, total_tables):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.sync_execution
            (tenant_id, store_id, execution_type, sync_mode,
             execution_status, total_tables, initiated_by, created_by)
            OUTPUT INSERTED.execution_id
            VALUES (?, ?, ?, ?, 'PENDING', ?, NULL, NULL)
            """,
            (tenant_id, store_id, execution_type, sync_mode, total_tables)
        )
        execution_id = cursor.fetchone()[0]
        _audit(cursor, execution_id, 'CREATED', 'Task created')
        conn.commit()
        return str(execution_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_pending_tasks(store_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT execution_id, tenant_id, store_id, execution_type,
                   sync_mode, execution_status, started_at, total_tables
            FROM dbo.sync_execution
            WHERE store_id = ?
              AND execution_status = 'PENDING'
            ORDER BY started_at ASC
            """,
            (store_id,)
        )
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        return [
            {
                **dict(zip(cols, row)),
                "execution_id": str(row[0]),
                "tenant_id": str(row[1]),
                "store_id": str(row[2]),
                "started_at": row[6].isoformat() if row[6] else None,
            }
            for row in rows
        ]
    finally:
        conn.close()


def _set_status(task_id, status, message, set_completed=False):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if set_completed:
            cursor.execute(
                """
                UPDATE dbo.sync_execution
                SET execution_status = ?, completed_at = GETDATE()
                WHERE execution_id = ?
                """,
                (status, task_id)
            )
        else:
            cursor.execute(
                """
                UPDATE dbo.sync_execution
                SET execution_status = ?
                WHERE execution_id = ?
                """,
                (status, task_id)
            )
        _audit(cursor, task_id, status, message)
        conn.commit()
        return {"task_id": task_id, "status": status}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def start_task(task_id):
    return _set_status(task_id, 'RUNNING', 'Task started')


def complete_task(task_id):
    return _set_status(task_id, 'COMPLETED', 'Task completed', set_completed=True)


def fail_task(task_id, message):
    return _set_status(task_id, 'FAILED', message, set_completed=True)


def get_configuration(task_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT execution_id, tenant_id, store_id, execution_type, sync_mode
            FROM dbo.sync_execution
            WHERE execution_id = ?
            """,
            (task_id,)
        )
        task = cursor.fetchone()
        if not task:
            return None

        cursor.execute(
            """
            SELECT sync_table_id, table_name, sync_mode, watermark_column,
                   window_days, window_months, custom_where, sync_order
            FROM sync.sync_table_master
            WHERE is_active = 1
            ORDER BY sync_order ASC
            """
        )
        tcols = [c[0] for c in cursor.description]
        tables = [dict(zip(tcols, r)) for r in cursor.fetchall()]

        for table in tables:
            table["sync_table_id"] = str(table["sync_table_id"])
            cursor.execute(
                """
                SELECT column_name, data_type, is_selected, is_pk,
                       is_hash, is_watermark, column_order
                FROM sync.sync_column_mapping
                WHERE sync_table_id = ?
                  AND is_selected = 1
                ORDER BY column_order ASC
                """,
                (table["sync_table_id"],)
            )
            ccols = [c[0] for c in cursor.description]
            table["columns"] = [
                dict(zip(ccols, r)) for r in cursor.fetchall()
            ]

        return {
            "task_id": str(task[0]),
            "tenant_id": str(task[1]),
            "store_id": str(task[2]),
            "execution_type": task[3],
            "sync_mode": task[4],
            "tables": tables,
        }
    finally:
        conn.close()


def _get_table_keys(cursor, sync_table_name):
    cursor.execute(
        """
        SELECT column_name, is_pk
        FROM sync.sync_column_mapping m
        INNER JOIN sync.sync_table_master t
            ON m.sync_table_id = t.sync_table_id
        WHERE t.table_name = ?
          AND m.is_selected = 1
        ORDER BY m.column_order ASC
        """,
        (sync_table_name,)
    )
    columns = []
    pk = []
    for row in cursor.fetchall():
        columns.append(row[0])
        if row[1]:
            pk.append(row[0])
    return columns, pk


def _diagnose_stage_failure(table_name, chunk_no, columns, staged,
                            column_meta, bulk_ex):
    """Locate the exact offending row/column on a fresh connection (the
    failed transaction is unusable) and return a JSON diagnostic string."""
    import json

    report = {
        "table": table_name,
        "chunk": chunk_no,
        "bulk_error": str(bulk_ex),
        "row_index": None,
        "column": None,
        "source_value": None,
        "destination_type": None,
        "column_error": None,
    }

    conn = get_connection()
    try:
        cursor = conn.cursor()
        for row_index, values in enumerate(staged):
            for column, value in zip(columns, values):
                meta = column_meta.get(column)
                cast_type = type_normalizer.cast_type(meta) if meta else "sql_variant"
                try:
                    cursor.execute("SELECT CAST(? AS " + cast_type + ")", (value,))
                    cursor.fetchall()
                except Exception as col_ex:
                    report.update(
                        {
                            "row_index": row_index,
                            "column": column,
                            "source_value": value,
                            "destination_type": cast_type,
                            "column_error": str(col_ex),
                        }
                    )
                    print(
                        "[CHUNK_DIAGNOSTIC] table=%s chunk=%s row=%s column=%s "
                        "value=%r dest_type=%s error=%s"
                        % (table_name, chunk_no, row_index, column, value,
                           cast_type, col_ex)
                    )
                    return json.dumps(report, default=str)
        return json.dumps(report, default=str)
    finally:
        conn.close()


def _upsert_table_progress(cursor, execution_id, table_name, sync_type,
                           total_rows, rows_delta):
    cursor.execute(
        """
        UPDATE sync.sync_table_progress
        SET total_rows = CASE WHEN ? > total_rows THEN ? ELSE total_rows END,
            rows_sent = rows_sent + ?,
            chunks_sent = chunks_sent + 1,
            sync_type = COALESCE(?, sync_type),
            updated_at = GETDATE()
        WHERE execution_id = ? AND table_name = ?
        """,
        (total_rows or 0, total_rows or 0, rows_delta, sync_type,
         execution_id, table_name)
    )
    if cursor.rowcount == 0:
        cursor.execute(
            """
            INSERT INTO sync.sync_table_progress
            (execution_id, table_name, sync_type, total_rows, rows_sent,
             chunks_sent, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, GETDATE())
            """,
            (execution_id, table_name, sync_type, total_rows or 0, rows_delta)
        )


def _accumulate_details(cursor, execution_id, table_name, sync_type,
                        merged, inserted, updated):
    """Accumulate HO-side merge metrics into the per-table summary row
    (chunk_no = 0) of sync_execution_details."""
    cursor.execute(
        """
        UPDATE dbo.sync_execution_details
        SET rows_processed = ISNULL(rows_processed, 0) + ?,
            rows_uploaded = ISNULL(rows_uploaded, 0) + ?,
            rows_inserted = ISNULL(rows_inserted, 0) + ?,
            rows_updated = ISNULL(rows_updated, 0) + ?,
            sync_type = COALESCE(?, sync_type),
            completed_at = GETDATE()
        WHERE execution_id = ? AND table_name = ? AND chunk_no = 0
        """,
        (merged, merged, inserted, updated, sync_type, execution_id, table_name)
    )
    if cursor.rowcount == 0:
        cursor.execute(
            "SELECT tenant_id, store_id FROM dbo.sync_execution WHERE execution_id = ?",
            (execution_id,)
        )
        owner = cursor.fetchone()
        tenant_id = owner[0] if owner else None
        store_id = owner[1] if owner else None
        cursor.execute(
            """
            INSERT INTO dbo.sync_execution_details
            (execution_id, tenant_id, store_id, table_name, chunk_no, chunk_size,
             rows_processed, rows_failed, rows_uploaded, rows_inserted,
             rows_updated, sync_type, status, started_at, created_at)
            VALUES (?, ?, ?, ?, 0, 0, ?, 0, ?, ?, ?, ?, 'RUNNING', GETDATE(), GETDATE())
            """,
            (execution_id, tenant_id, store_id, table_name, merged, merged,
             inserted, updated, sync_type)
        )


def report_table_metrics(execution_id, table_name, sync_type, rows_examined,
                         rows_changed, rows_uploaded, rows_skipped, source_total):
    """Agent-reported per-table delta metrics (examined/changed/skipped)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.sync_execution_details
            SET rows_examined = ?, rows_changed = ?, rows_skipped = ?,
                source_total = ?, sync_type = COALESCE(?, sync_type),
                completed_at = GETDATE()
            WHERE execution_id = ? AND table_name = ? AND chunk_no = 0
            """,
            (rows_examined, rows_changed, rows_skipped, source_total,
             sync_type, execution_id, table_name)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT tenant_id, store_id FROM dbo.sync_execution WHERE execution_id = ?",
                (execution_id,)
            )
            owner = cursor.fetchone()
            tenant_id = owner[0] if owner else None
            store_id = owner[1] if owner else None
            cursor.execute(
                """
                INSERT INTO dbo.sync_execution_details
                (execution_id, tenant_id, store_id, table_name, chunk_no, chunk_size,
                 rows_processed, rows_failed, rows_examined, rows_changed,
                 rows_uploaded, rows_skipped, source_total, sync_type, status,
                 started_at, created_at)
                VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?, 0, ?, ?, ?, 'RUNNING', GETDATE(), GETDATE())
                """,
                (execution_id, tenant_id, store_id, table_name, rows_examined,
                 rows_changed, rows_skipped, source_total, sync_type)
            )
        conn.commit()
        return {"execution_id": execution_id, "table_name": table_name,
                "rows_examined": rows_examined, "rows_changed": rows_changed,
                "rows_skipped": rows_skipped}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_table_statistics():
    """Per-table statistics for the Table Statistics tab: source rows,
    HO rows, changed today, uploaded/updated today, last sync."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sync_table_id, table_name, sync_mode, is_active, watermark_column
            FROM sync.sync_table_master
            WHERE is_active = 1
            ORDER BY sync_order
            """
        )
        tables = cursor.fetchall()

        result = []
        for sync_table_id, table_name, sync_mode, is_active, watermark_column in tables:
            # HO physical row count + last synced business value (high watermark).
            ho_rows = 0
            last_business_value = None
            cursor.execute("SELECT OBJECT_ID(?, 'U')", ("sync." + table_name,))
            if cursor.fetchone()[0] is not None:
                cursor.execute("SELECT COUNT(*) FROM sync.[" + table_name + "]")
                ho_rows = cursor.fetchone()[0]
                # Latest business value on the configured watermark column, if any.
                if watermark_column:
                    try:
                        cursor.execute(
                            "SELECT CONVERT(nvarchar(64), MAX([" + watermark_column + "])) "
                            "FROM sync.[" + table_name + "]"
                        )
                        last_business_value = cursor.fetchone()[0]
                    except Exception:
                        last_business_value = None

            cursor.execute(
                """
                SELECT
                    ISNULL(SUM(rows_examined), 0),
                    ISNULL(SUM(rows_changed), 0),
                    ISNULL(SUM(rows_uploaded), 0),
                    ISNULL(SUM(rows_inserted), 0),
                    ISNULL(SUM(rows_updated), 0),
                    ISNULL(SUM(rows_skipped), 0),
                    MAX(source_total),
                    MAX(completed_at)
                FROM dbo.sync_execution_details
                WHERE table_name = ? AND chunk_no = 0
                  AND CAST(created_at AS DATE) = CAST(GETDATE() AS DATE)
                """,
                (table_name,)
            )
            today = cursor.fetchone()

            cursor.execute(
                """
                SELECT MAX(completed_at) FROM dbo.sync_execution_details
                WHERE table_name = ? AND chunk_no = 0
                """,
                (table_name,)
            )
            last_sync = cursor.fetchone()[0]

            result.append({
                "table_name": table_name,
                "sync_mode": sync_mode,
                "source_rows": int(today[6]) if today[6] else None,
                "ho_rows": int(ho_rows),
                "changed_today": int(today[1]),
                "examined_today": int(today[0]),
                "uploaded_today": int(today[2]),
                "inserted_today": int(today[3]),
                "updated_today": int(today[4]),
                "skipped_today": int(today[5]),
                "last_sync": last_sync.isoformat() if last_sync else None,
                "watermark_column": watermark_column,
                "last_business_value": last_business_value,
            })
        return result
    finally:
        conn.close()


def upload_chunk(execution_id, table_name, chunk_no, rows,
                 total_rows=None, sync_type=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO dbo.sync_chunk_execution
            (execution_id, table_name, chunk_no, chunk_status,
             rows_processed, started_at)
            OUTPUT INSERTED.chunk_execution_id
            VALUES (?, ?, ?, 'RECEIVED', 0, GETDATE())
            """,
            (execution_id, table_name, chunk_no)
        )
        chunk_execution_id = cursor.fetchone()[0]

        # HO derives store context from the execution (never trusts the row).
        cursor.execute(
            "SELECT tenant_id, store_id FROM dbo.sync_execution WHERE execution_id = ?",
            (execution_id,)
        )
        owner = cursor.fetchone()
        tenant_id = str(owner[0]) if owner and owner[0] else None
        store_id = str(owner[1]) if owner and owner[1] else None

        # Phase 028D: ensure the store-scoped shared table exists before merge.
        schema_evolution.ensure_table(cursor, table_name)

        columns, pk = _get_table_keys(cursor, table_name)

        # Target physical schema drives column resolution, typing and scale.
        column_meta = type_normalizer.get_target_column_meta(
            cursor, "sync", table_name
        )

        if not columns:
            columns = [
                c for c in (list(rows[0].keys()) if rows else [])
                if c not in ("store_id", "tenant_id", "row_hash")
            ]

        # Schema-version resilience: only sync columns that physically exist
        # in the shared target table. Stores that lack a column simply omit it.
        columns = [c for c in columns if c in column_meta]
        pk = [c for c in pk if c in column_meta]

        # Context columns are stamped on every staged row (Phase 029C/D).
        stage_cols = columns + ["store_id", "tenant_id", "row_hash"]

        merged = 0
        inserted = 0
        updated = 0
        if rows and columns:
            collist = ", ".join("[" + c + "]" for c in stage_cols)
            placeholders = ",".join("?" for _ in stage_cols)

            cursor.execute(
                "SELECT TOP 0 " + collist +
                " INTO #stage FROM sync.[" + table_name + "]"
            )

            # Normalize business columns, then append store context per row.
            business = type_normalizer.normalize_rows(rows, columns, column_meta)
            staged = [
                tuple(vals) + (store_id, tenant_id, row.get("row_hash"))
                for vals, row in zip(business, rows)
            ]

            insert_sql = (
                "INSERT INTO #stage (" + collist + ") VALUES (" +
                placeholders + ")"
            )
            try:
                cursor.fast_executemany = True
                # Pin decimal precision/scale per column so fast_executemany
                # binds the whole array against the true column definition.
                sizes = []
                has_decimal = False
                for c in stage_cols:
                    meta = column_meta.get(c) or {}
                    if meta.get("type") in ("decimal", "numeric"):
                        has_decimal = True
                        sizes.append(
                            (
                                pyodbc.SQL_DECIMAL,
                                meta.get("precision") or 38,
                                meta.get("scale") or 0,
                            )
                        )
                    else:
                        sizes.append(None)
                if has_decimal:
                    cursor.setinputsizes(sizes)
                cursor.executemany(insert_sql, staged)
                if has_decimal:
                    cursor.setinputsizes(None)
            except Exception as bulk_ex:
                detail = _diagnose_stage_failure(
                    table_name, chunk_no, stage_cols, staged, column_meta, bulk_ex
                )
                raise RuntimeError("CHUNK_STAGE_FAILED " + detail)

            insert_cols = ", ".join("[" + c + "]" for c in stage_cols)
            insert_vals = ", ".join("S.[" + c + "]" for c in stage_cols)
            if pk:
                # Merge key = store_id + business PK (multi-store isolation).
                key_cols = ["store_id"] + pk
                on = " AND ".join(
                    "T.[" + k + "]=S.[" + k + "]" for k in key_cols
                )
                non_key = [c for c in stage_cols if c not in key_cols]
                merge = (
                    "SET NOCOUNT ON;"
                    "DECLARE @act TABLE(act NVARCHAR(10));"
                    "MERGE sync.[" + table_name + "] AS T "
                    "USING #stage AS S ON " + on + " "
                )
                if non_key:
                    update_set = ", ".join(
                        "T.[" + c + "]=S.[" + c + "]" for c in non_key
                    )
                    merge += "WHEN MATCHED THEN UPDATE SET " + update_set + " "
                merge += (
                    "WHEN NOT MATCHED THEN INSERT (" + insert_cols + ") "
                    "VALUES (" + insert_vals + ") "
                    "OUTPUT $action INTO @act;"
                    "SELECT "
                    "SUM(CASE WHEN act='INSERT' THEN 1 ELSE 0 END),"
                    "SUM(CASE WHEN act='UPDATE' THEN 1 ELSE 0 END) FROM @act;"
                )
                cursor.execute(merge)
                counts = cursor.fetchone()
                inserted = int(counts[0] or 0)
                updated = int(counts[1] or 0)
                cursor.execute("SET NOCOUNT OFF")
            else:
                cursor.execute(
                    "INSERT INTO sync.[" + table_name + "] (" + insert_cols + ") "
                    "SELECT " + insert_cols + " FROM #stage"
                )
                inserted = len(rows)

            merged = len(rows)
            cursor.execute("DROP TABLE #stage")

        cursor.execute(
            """
            UPDATE dbo.sync_chunk_execution
            SET chunk_status = 'MERGED',
                rows_processed = ?,
                completed_at = GETDATE()
            WHERE chunk_execution_id = ?
            """,
            (merged, chunk_execution_id)
        )

        _upsert_table_progress(
            cursor, execution_id, table_name, sync_type, total_rows, merged
        )
        _accumulate_details(
            cursor, execution_id, table_name, sync_type, merged, inserted, updated
        )

        _audit(
            cursor, execution_id, 'CHUNK_MERGED',
            table_name + " chunk " + str(chunk_no) + " rows " + str(merged) +
            " (+" + str(inserted) + "/~" + str(updated) + ")"
        )
        conn.commit()
        print(
            "[HO]   %-24s | chunk=%-4d rows=%-6d inserted=%-6d updated=%-6d"
            % (table_name, chunk_no, merged, inserted, updated),
            flush=True,
        )
        return {
            "chunk_execution_id": int(chunk_execution_id),
            "table_name": table_name,
            "chunk_no": chunk_no,
            "rows_processed": merged,
            "rows_inserted": inserted,
            "rows_updated": updated,
            "status": "MERGED",
        }
    except Exception as ex:
        conn.rollback()
        conn2 = get_connection()
        try:
            c2 = conn2.cursor()
            c2.execute(
                """
                INSERT INTO dbo.sync_chunk_execution
                (execution_id, table_name, chunk_no, chunk_status,
                 rows_processed, started_at, completed_at, error_message)
                VALUES (?, ?, ?, 'FAILED', 0, GETDATE(), GETDATE(), ?)
                """,
                (execution_id, table_name, chunk_no, str(ex))
            )
            conn2.commit()
        finally:
            conn2.close()
        raise
    finally:
        conn.close()


def ack_chunk(chunk_execution_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.sync_chunk_execution
            SET chunk_status = 'ACK', completed_at = GETDATE()
            WHERE chunk_execution_id = ?
            """,
            (chunk_execution_id,)
        )
        conn.commit()
        return {"chunk_execution_id": chunk_execution_id, "status": "ACK"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def agent_heartbeat(tenant_id, store_id, agent_version=None,
                    connection_type=None, ip_address=None, register=False,
                    install_path=None, hostname=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        if not tenant_id:
            cursor.execute(
                "SELECT tenant_id FROM dbo.stores WHERE store_id = ?",
                (store_id,)
            )
            found = cursor.fetchone()
            if not found:
                raise ValueError("Unknown store_id: " + str(store_id))
            tenant_id = found[0]

        cursor.execute(
            """
            UPDATE dbo.store_agent_registry
            SET last_heartbeat = GETDATE(),
                connection_status = 'ONLINE',
                is_active = 1,
                agent_version = COALESCE(?, agent_version),
                connection_type = COALESCE(?, connection_type)
            WHERE store_id = ?
            """,
            (agent_version, connection_type, store_id)
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO dbo.store_agent_registry
                (tenant_id, store_id, agent_version, connection_type,
                 installed_at, last_heartbeat, connection_status, is_active)
                VALUES (?, ?, ?, ?, GETDATE(), GETDATE(), 'ONLINE', 1)
                """,
                (tenant_id, store_id, agent_version, connection_type)
            )

        cursor.execute(
            """
            INSERT INTO dbo.agent_heartbeat_log
            (tenant_id, store_id, heartbeat_time, ip_address, agent_version)
            VALUES (?, ?, GETDATE(), ?, ?)
            """,
            (tenant_id, store_id, ip_address, agent_version)
        )

        # On registration, record where the agent is installed so HO can track
        # / push updates later without re-installing on every store.
        if register and install_path:
            cursor.execute(
                """
                UPDATE dbo.stores
                SET agent_install_path = ?,
                    agent_hostname = COALESCE(?, agent_hostname),
                    agent_registered_at = GETDATE()
                WHERE store_id = ?
                """,
                (install_path, hostname, store_id)
            )

        conn.commit()
        return {
            "store_id": store_id,
            "connection_status": "ONLINE",
            "registered": register or cursor.rowcount == 0,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_stale_agents_offline(threshold_seconds=300):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.store_agent_registry
            SET connection_status = 'OFFLINE'
            WHERE is_active = 1
              AND (last_heartbeat IS NULL
                   OR last_heartbeat < DATEADD(SECOND, ?, GETDATE()))
              AND connection_status <> 'OFFLINE'
            """,
            (-abs(threshold_seconds),)
        )
        affected = cursor.rowcount
        conn.commit()
        return {"marked_offline": affected}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_live_status():
    """Live progress for RUNNING executions, keyed per store. Real totals,
    rows-remaining, ETA and progress come from sync.sync_table_progress
    (agent-reported per-table totals)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT e.execution_id, e.store_id, s.store_code, s.store_name,
                   e.execution_status, e.started_at,
                   DATEDIFF(SECOND, e.started_at, GETDATE()) AS elapsed
            FROM dbo.sync_execution e
            LEFT JOIN dbo.stores s ON s.store_id = e.store_id
            WHERE e.execution_status IN ('RUNNING', 'PAUSED')
            """
        )
        executions = cursor.fetchall()

        result = []
        for (execution_id, store_id, store_code, store_name, status,
             started_at, elapsed) in executions:

            cursor.execute(
                """
                SELECT TOP 1 table_name, chunk_no
                FROM dbo.sync_chunk_execution
                WHERE execution_id = ?
                ORDER BY chunk_execution_id DESC
                """,
                (execution_id,)
            )
            latest = cursor.fetchone()
            current_table = latest[0] if latest else None
            chunk_no = latest[1] if latest else None

            # Whole-execution rows + per-current-table totals.
            cursor.execute(
                """
                SELECT
                    (SELECT ISNULL(SUM(rows_sent), 0)
                       FROM sync.sync_table_progress WHERE execution_id = ?),
                    (SELECT ISNULL(SUM(total_rows), 0)
                       FROM sync.sync_table_progress WHERE execution_id = ?)
                """,
                (execution_id, execution_id)
            )
            exec_sent, exec_total = cursor.fetchone()
            exec_sent = int(exec_sent or 0)
            exec_total = int(exec_total or 0)

            cur_total = 0
            cur_sent = 0
            chunks_sent = 0
            sync_type = None
            if current_table:
                cursor.execute(
                    """
                    SELECT total_rows, rows_sent, chunks_sent, sync_type
                    FROM sync.sync_table_progress
                    WHERE execution_id = ? AND table_name = ?
                    """,
                    (execution_id, current_table)
                )
                row = cursor.fetchone()
                if row:
                    cur_total = int(row[0] or 0)
                    cur_sent = int(row[1] or 0)
                    chunks_sent = int(row[2] or 0)
                    sync_type = row[3]

            # Delta metrics for the current table (Live Operations columns).
            rows_changed = 0
            rows_uploaded = 0
            rows_inserted = 0
            rows_updated = 0
            if current_table:
                cursor.execute(
                    """
                    SELECT ISNULL(rows_changed, 0), ISNULL(rows_uploaded, 0),
                           ISNULL(rows_inserted, 0), ISNULL(rows_updated, 0)
                    FROM dbo.sync_execution_details
                    WHERE execution_id = ? AND table_name = ? AND chunk_no = 0
                    """,
                    (execution_id, current_table)
                )
                drow = cursor.fetchone()
                if drow:
                    rows_changed = int(drow[0])
                    rows_uploaded = int(drow[1])
                    rows_inserted = int(drow[2])
                    rows_updated = int(drow[3])

            elapsed = int(elapsed or 0)
            speed = round(exec_sent / elapsed, 1) if elapsed > 0 else 0.0
            rows_remaining = max(exec_total - exec_sent, 0) if exec_total else None
            eta_seconds = (
                int(rows_remaining / speed)
                if rows_remaining and speed > 0 else None
            )
            progress = (
                min(100.0, round((exec_sent / exec_total) * 100, 2))
                if exec_total else 0.0
            )
            avg_chunk = (cur_sent / chunks_sent) if chunks_sent else 0
            total_chunks = (
                int(-(-cur_total // avg_chunk)) if avg_chunk and cur_total else None
            )

            result.append({
                "store_id": str(store_id),
                "store_code": store_code,
                "store_name": store_name,
                "execution_id": str(execution_id),
                "status": status,
                "sync_type": sync_type,
                "current_table": current_table,
                "chunk_no": chunk_no,
                "total_chunks": total_chunks,
                "chunk_size": int(avg_chunk) if avg_chunk else None,
                "rows_processed": exec_sent,
                "total_rows": exec_total or None,
                "rows_remaining": rows_remaining,
                "rows_changed": rows_changed,
                "rows_uploaded": rows_uploaded,
                "rows_inserted": rows_inserted,
                "rows_updated": rows_updated,
                "speed_rows_sec": speed,
                "eta_seconds": eta_seconds,
                "progress_pct": progress,
                "started_at": started_at.isoformat() if started_at else None,
                "updated_at": _now_iso(),
            })

        return result
    finally:
        conn.close()


def _now_iso():
    import datetime
    return datetime.datetime.now().isoformat()


def control_stores(store_ids, action):
    """Bulk control of running syncs for a set of stores.
    action: 'PAUSE' -> PAUSED, 'STOP' -> CANCELLED."""
    if not store_ids:
        return {"affected": 0, "action": action}
    status = "PAUSED" if action == "PAUSE" else "CANCELLED"
    completed = "" if action == "PAUSE" else ", completed_at = GETDATE()"
    conn = get_connection()
    try:
        cursor = conn.cursor()
        affected = 0
        for store_id in store_ids:
            cursor.execute(
                "UPDATE dbo.sync_execution SET execution_status = ?" + completed +
                " WHERE store_id = ? AND execution_status IN ('RUNNING','PAUSED','PENDING')",
                (status, store_id)
            )
            affected += cursor.rowcount
        conn.commit()
        return {"affected": affected, "action": action, "status": status}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_chunk_status(execution_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT chunk_execution_id, table_name, chunk_no, chunk_status,
                   rows_processed, started_at, completed_at, error_message
            FROM dbo.sync_chunk_execution
            WHERE execution_id = ?
            ORDER BY chunk_execution_id ASC
            """,
            (execution_id,)
        )
        cols = [c[0] for c in cursor.description]
        out = []
        for row in cursor.fetchall():
            item = dict(zip(cols, row))
            item["started_at"] = (
                row[5].isoformat() if row[5] else None
            )
            item["completed_at"] = (
                row[6].isoformat() if row[6] else None
            )
            out.append(item)
        return out
    finally:
        conn.close()
