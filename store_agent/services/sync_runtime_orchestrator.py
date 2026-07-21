from store_agent.services.task_polling_service import TaskPollingService
from store_agent.services.catalog_sync_service import CatalogSyncService
from store_agent.services.data_extraction_service import DataExtractionService
from store_agent.services.hash_generation_service import HashGenerationService
from store_agent.services.chunk_builder_service import ChunkBuilderService
from store_agent.services.sync_sender_service import SyncSenderService
from store_agent.services.sync_ack_processor import SyncAckProcessor
from store_agent.services.sqlite_cache_service import SqliteCacheService

_MASTER_MODES = ("UPSERT", "FULL", "MASTER")
_WATERMARK_MODES = ("ROLLING_WINDOW", "INCREMENTAL", "DELTA")


class SyncRuntimeOrchestrator:
    """SYNC Runtime V2 - true delta sync orchestrator.

    Master tables  -> per-row hash diff vs SQLite cache; upload only changed.
    Txn  tables    -> watermark (>last_watermark, rolling-window floor first run).
    """

    def __init__(self, connection, ho_api_url, store_id, chunk_size=1000):
        self.connection = connection
        self.store_id = store_id
        self.polling = TaskPollingService(ho_api_url)
        self.catalog = CatalogSyncService(ho_api_url)
        self.extractor = DataExtractionService(connection)
        self.hasher = HashGenerationService()
        self.chunker = ChunkBuilderService(chunk_size)
        self.sender = SyncSenderService(ho_api_url)
        self.ack = SyncAckProcessor(ho_api_url)
        # Cache is store-scoped: identity is (store_id, table_name, source_pk).
        self.cache = SqliteCacheService(store_id=store_id)

    def run_cycle(self):
        self.flush_pending()
        tasks = self.polling.poll(self.store_id)
        results = []
        for task in tasks:
            results.append(self.run_task(task["execution_id"]))
        return {"tasks_processed": len(tasks), "results": results}

    def run_task(self, task_id):
        self.polling.start(task_id)
        self.cache.record_execution(task_id, "RUNNING")
        try:
            config = self.catalog.download_configuration(task_id)
            # 028B: persist HO configuration into SQLite (single source = HO).
            tables = config.get("tables", [])
            self.cache.save_sync_config(tables)
        except Exception as ex:
            # Only a failure to obtain the configuration aborts the whole task —
            # there is nothing to iterate. Per-table errors never abort (below).
            try:
                self.polling.fail(task_id, "CONFIG_DOWNLOAD_FAILED: " + str(ex))
            except Exception:
                pass
            self.cache.record_execution(task_id, "FAILED", completed=True)
            return {"task_id": task_id, "status": "FAILED", "error": str(ex)}

        total = len(tables)
        completed = failed = skipped = 0
        table_results = []
        print("[SYNC] === FULL SYNC START tables=%d ===" % total, flush=True)

        # Per-table isolation: one failing/absent table must never stop the rest.
        # Every enabled table in the configuration is attempted, in order.
        for table in tables:
            name = table.get("table_name", "?")
            outcome = self.run_table_safe(task_id, table)
            table_results.append(outcome)
            state = outcome.get("state")
            if state == "COMPLETED":
                completed += 1
            elif state == "SKIPPED":
                skipped += 1
            else:
                failed += 1
            print(
                "[SYNC] %-24s | %-9s | %s"
                % (name, state, outcome.get("message", "")),
                flush=True,
            )

        # The execution finished (it did not abort). Per-table failures are
        # recorded individually; the run itself completes with a summary.
        self.polling.complete(task_id)
        self.cache.record_execution(task_id, "COMPLETED", completed=True)
        print(
            "[SYNC] === FULL SYNC DONE total=%d completed=%d skipped=%d failed=%d ==="
            % (total, completed, skipped, failed),
            flush=True,
        )
        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "summary": {
                "total_tables": total,
                "completed": completed,
                "skipped": skipped,
                "failed": failed,
            },
            "tables": table_results,
        }

    def run_table_safe(self, task_id, table):
        """Run one table with full isolation + timing. Never raises: a failure
        is captured, reported to HO, logged, and returned so the caller can move
        on to the next table."""
        import time
        name = table.get("table_name", "?")
        started = time.time()
        print("[SYNC] %-24s | STARTED" % name, flush=True)
        try:
            result = self.run_table(task_id, table)
            result["state"] = "COMPLETED"
            result["duration_sec"] = round(time.time() - started, 2)
            result["message"] = (
                "examined=%s changed=%s uploaded=%s skipped=%s dur=%ss"
                % (result.get("examined"), result.get("changed"),
                   result.get("uploaded"), result.get("skipped"),
                   result["duration_sec"])
            )
            print(
                "[SYNC] %-24s | COMPLETED | %s" % (name, result["message"]),
                flush=True,
            )
            return result
        except Exception as ex:
            duration = round(time.time() - started, 2)
            reason = str(ex)
            print(
                "[SYNC] %-24s | FAILED    | %s (dur=%ss)" % (name, reason, duration),
                flush=True,
            )
            # Record the per-table failure at HO so history never shows a silent
            # gap (best-effort; a reporting error must not abort the sequence).
            # Without status/error_message this looked identical to a healthy
            # empty sync in HO's dashboard, so a table that kept crashing every
            # cycle (e.g. ProductTrans) went stale for days with no visible sign.
            try:
                self._report(task_id, name, table.get("sync_mode"),
                             0, 0, 0, 0, 0, status="FAILED", error_message=reason)
            except Exception:
                pass
            try:
                self.cache.log_execution(task_id, name, 0, 0, 0, 0)
            except Exception:
                pass
            return {
                "table_name": name,
                "state": "FAILED",
                "error": reason,
                "duration_sec": duration,
                "message": reason,
            }

    def run_table(self, task_id, table):
        sync_mode = (table.get("sync_mode") or "").upper()
        watermark = None
        if sync_mode in _WATERMARK_MODES and table.get("watermark_column"):
            # Rolling window: extract only rows in the window / past watermark.
            watermark = self.cache.get_last_watermark(table["table_name"])
            # Backfill when the rolling window grows. The stored watermark is
            # forward-only, so simply increasing window_days (e.g. 60 -> 180)
            # would never pull the older rows. If the configured window is
            # wider than the one last applied (or unknown after an upgrade),
            # drop the watermark for this run so the full window is re-extracted
            # once; incremental resumes automatically afterwards.
            window = table.get("window_days")
            if window:
                key = "wm_window:" + table["table_name"]
                prev = self.cache.get_config(key)
                try:
                    prev_window = int(prev) if prev not in (None, "") else None
                except (TypeError, ValueError):
                    prev_window = None
                if prev_window is None or int(window) > prev_window:
                    watermark = None
                self.cache.set_config(key, str(int(window)))
        extracted = self.extractor.extract(table, watermark=watermark)
        return self._diff_and_upload(task_id, table, extracted, sync_mode)

    @staticmethod
    def _hash_columns(cols):
        """Phase 029A: only is_hash=1 columns participate in the row hash.
        Falls back to all selected columns if none are flagged."""
        marked = [c["column_name"] for c in cols if c.get("is_hash")]
        return marked or [c["column_name"] for c in cols]

    def _diff_and_upload(self, task_id, table, extracted, sync_mode):
        table_name = table["table_name"]
        cols = table.get("columns", [])
        pk_cols = [c["column_name"] for c in cols if c.get("is_pk")]
        hash_cols = self._hash_columns(cols)

        rows = extracted["rows"]
        examined = len(rows)

        cached = self.cache.get_row_hashes(table_name)
        changed_rows = []
        changed_hashes = []
        for row in rows:
            pk = self._pk_value(row, pk_cols)
            row_hash = self.hasher.compute_row_hash(row, hash_cols)
            if cached.get(pk) != row_hash:
                row["row_hash"] = row_hash
                changed_rows.append(row)
                changed_hashes.append((pk, row_hash))

        chunks = self.chunker.build(changed_rows)
        skipped = examined - len(changed_rows)
        strategy = "WATERMARK_HASH" if sync_mode in _WATERMARK_MODES else "MASTER_HASH"
        source_max = self._source_max(table_name, pk_cols)

        print(
            "[SYNC] %-24s | %-14s | examined=%-7d changed=%-6d "
            "uploaded=%-6d skipped=%-7d chunks=%-4d | source_max(%s)=%s"
            % (table_name, strategy, examined, len(changed_rows),
               len(changed_rows), skipped, len(chunks),
               ",".join(pk_cols) or "pk", source_max),
            flush=True,
        )

        uploaded = self._send_chunks(
            task_id, table_name, chunks, len(changed_rows),
            table.get("sync_mode"),
        )

        # Persist hashes / advance watermark only after successful upload.
        self.cache.upsert_row_hashes(table_name, changed_hashes)
        if sync_mode in _WATERMARK_MODES:
            if extracted.get("max_watermark") is not None:
                self.cache.set_last_watermark(table_name, extracted["max_watermark"])
        else:
            self.cache.mark_full_sync(table_name)
        self.cache.log_execution(task_id, table_name, examined,
                                 len(changed_rows), uploaded, skipped)
        self._report(task_id, table_name, table.get("sync_mode"), examined,
                     len(changed_rows), uploaded, skipped, examined)

        return {"table_name": table_name, "strategy": strategy,
                "examined": examined, "changed": len(changed_rows),
                "uploaded": uploaded, "skipped": skipped}

    # ---- transport (with offline outbox) ----------------------------------

    def _send_chunks(self, execution_id, table_name, chunks, total_rows, sync_type):
        uploaded = 0
        for chunk_no, chunk in enumerate(chunks, start=1):
            queue_id = self.cache.queue_chunk(
                execution_id, table_name, chunk_no, chunk, total_rows, sync_type
            )
            response = self.sender.send_chunk(
                execution_id, table_name, chunk_no, chunk,
                total_rows=total_rows, sync_type=sync_type,
            )
            chunk_execution_id = response.get("chunk_execution_id")
            if chunk_execution_id is not None:
                self.ack.ack(chunk_execution_id)
                self.cache.record_ack(
                    chunk_execution_id, execution_id, table_name, chunk_no
                )
            self.cache.mark_chunk_done(queue_id)
            uploaded += len(chunk)
        return uploaded

    def flush_pending(self):
        for pending in self.cache.get_pending_chunks():
            try:
                response = self.sender.send_chunk(
                    pending["execution_id"], pending["table_name"],
                    pending["chunk_no"], pending["payload"],
                    total_rows=pending["total_rows"],
                    sync_type=pending["sync_type"],
                )
                chunk_execution_id = response.get("chunk_execution_id")
                if chunk_execution_id is not None:
                    self.ack.ack(chunk_execution_id)
                self.cache.mark_chunk_done(pending["chunk_id"])
            except Exception:
                break  # HO still unreachable; retry next cycle

    def _report(self, execution_id, table_name, sync_type, examined, changed,
                uploaded, skipped, source_total, status="COMPLETED",
                error_message=None):
        try:
            self.sender.report_table_metrics(
                execution_id, table_name, sync_type, examined, changed,
                uploaded, skipped, source_total,
                status=status, error_message=error_message,
            )
        except Exception:
            pass  # metrics are best-effort, never fail a sync

    def _source_max(self, table_name, pk_cols):
        """Max business PK on the store source DB (for both-sides verification)."""
        if not pk_cols or self.connection is None:
            return "n/a"
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT MAX([" + pk_cols[0] + "]) FROM [" + table_name + "]"
            )
            value = cursor.fetchone()[0]
            return "NULL" if value is None else str(value)
        except Exception:
            return "err"

    @staticmethod
    def _pk_value(row, pk_cols):
        if not pk_cols:
            return "|".join("" if v is None else str(v) for v in row.values())
        return "|".join("" if row.get(c) is None else str(row.get(c)) for c in pk_cols)
