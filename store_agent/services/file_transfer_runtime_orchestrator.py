"""FILE_TRANSFER sync orchestrator.

Reuses the exact engine SyncRuntimeOrchestrator uses for DIRECT_HTTP --
DataExtractionService (extraction), HashGenerationService (row hashing),
ChunkBuilderService (chunking), SqliteCacheService (row-hash/watermark cache
and, for this mode, the package outbox), and even SyncRuntimeOrchestrator's
own hashing/pk-value static helpers -- so a store never gets a different diff
result depending on which transport happens to be configured. The only thing
that differs is where a cycle's changed rows go: DIRECT_HTTP posts each chunk
to HO immediately (store_agent/services/sync_runtime_orchestrator.py);
FILE_TRANSFER batches every table's chunks from one cycle into a single
package (store_agent/file_transfer/package_builder.py) and hands it to a
Transport adapter instead of talking to HO in real time.

Known deliberate scope reduction vs. the DIRECT_HTTP engine: the
ProductSaleInformation/SaleInformation linked-cursor optimization and
per-table source_max verification are DIRECT_HTTP-only observability/
performance refinements, not correctness rules -- they are not reproduced
here. Every table still gets a full, correct hash/watermark diff.
"""
import time
import uuid

from store_agent.services.data_extraction_service import DataExtractionService
from store_agent.services.hash_generation_service import HashGenerationService
from store_agent.services.chunk_builder_service import ChunkBuilderService
from store_agent.services.sync_runtime_orchestrator import (
    SyncRuntimeOrchestrator, _MASTER_MODES, _WATERMARK_MODES,
)
from store_agent.file_transfer.package_builder import PackageBuilder

_DEFAULT_CHUNK_SIZE = 1000


class FileTransferRuntimeOrchestrator:
    def __init__(self, connection, store_id, tenant_id, cache, outbox,
                agent_version="unknown", chunk_size=_DEFAULT_CHUNK_SIZE):
        self.connection = connection
        self.store_id = store_id
        self.tenant_id = tenant_id
        self.cache = cache
        self.outbox = outbox
        self.extractor = DataExtractionService(connection)
        self.hasher = HashGenerationService()
        self.chunker = ChunkBuilderService(chunk_size)
        self.builder = PackageBuilder(store_id, tenant_id, agent_version)

    def run_cycle(self):
        """At most one package per call. Table/column selection comes from
        the locally cached HO configuration (SqliteCacheService.
        get_active_table_config -- populated by the last successful
        save_sync_config, whether that happened via DIRECT_HTTP or a one-time
        bootstrap). A store with no cached configuration yet cannot produce a
        FILE_TRANSFER package until it has one."""
        tables = self.cache.get_active_table_config()
        if not tables:
            return {"status": "SKIPPED", "reason": "NO_CACHED_CONFIG"}

        execution_id = str(uuid.uuid4())
        table_summaries = []
        payload_chunks = []
        for table in tables:
            name = table.get("table_name", "?")
            try:
                summary, chunks = self._run_table(execution_id, table)
                table_summaries.append(summary)
                payload_chunks.extend(chunks)
            except Exception as ex:
                table_summaries.append({
                    "table_name": name, "sync_mode": table.get("sync_mode"),
                    "status": "FAILED", "error_message": str(ex),
                    "examined": 0, "changed": 0, "uploaded": 0, "skipped": 0,
                    "chunk_count": 0,
                })

        if not payload_chunks:
            return {"status": "NO_CHANGES", "execution_id": execution_id,
                    "tables": table_summaries}

        seq = self.cache.next_package_sequence()
        zip_path, manifest = self.builder.build(
            execution_id, table_summaries, payload_chunks,
            out_dir=str(self.outbox.pending_dir), seq=seq,
        )
        checksum = _sha256_file(zip_path)
        self.outbox.enqueue(
            manifest["package_id"], execution_id, zip_path, checksum,
            manifest["totals"]["total_rows"], manifest["totals"]["total_chunks"],
        )
        # Persist hashes/watermarks now: the package has been durably queued
        # in the outbox (survives a crash before transport send), matching
        # DIRECT_HTTP's "persist only after the upload attempt is queued"
        # ordering in sync_runtime_orchestrator._diff_and_upload.
        return {"status": "PACKAGED", "execution_id": execution_id,
                "package_id": manifest["package_id"], "zip_path": zip_path,
                "tables": table_summaries}

    def _run_table(self, execution_id, table):
        sync_mode = (table.get("sync_mode") or "").upper()
        table_name = table["table_name"]
        watermark = None
        if sync_mode in _WATERMARK_MODES and table.get("watermark_column"):
            watermark = self.cache.get_last_watermark(table_name)

        extracted = self.extractor.extract(table, watermark=watermark)
        rows = extracted["rows"]
        examined = len(rows)

        cols = table.get("columns", [])
        pk_cols = [c["column_name"] for c in cols if c.get("is_pk")]
        hash_cols = SyncRuntimeOrchestrator._hash_columns(cols)

        cached = self.cache.get_row_hashes(table_name)
        changed_rows = []
        changed_hashes = []
        all_hashes = []
        for row in rows:
            pk = SyncRuntimeOrchestrator._pk_value(row, pk_cols)
            row_hash = self.hasher.compute_row_hash(row, hash_cols)
            all_hashes.append((pk, row_hash))
            if cached.get(pk) != row_hash:
                row["row_hash"] = row_hash
                changed_rows.append(row)
                changed_hashes.append((pk, row_hash))

        chunks = self.chunker.build(changed_rows)
        skipped = examined - len(changed_rows)

        payload_chunks = [
            (
                table_name, chunk_no,
                {
                    "execution_id": execution_id, "table_name": table_name,
                    "chunk_no": chunk_no, "rows": chunk,
                    "total_rows": len(changed_rows), "sync_type": table.get("sync_mode"),
                },
            )
            for chunk_no, chunk in enumerate(chunks, start=1)
        ]

        # Persist hashes / advance watermark now -- mirrors DIRECT_HTTP's
        # "only after the chunks are queued for delivery" ordering; if the
        # package later fails to transport, the outbox retries the same zip
        # (idempotent on HO by package_id), it does not recompute the diff.
        # Touch ALL extracted rows (not just changed_hashes): prune_stale_row_hashes
        # relies on last_sync_time meaning "last seen in an extract", not "last
        # changed" -- an unchanged row inside the window must still get refreshed.
        self.cache.upsert_row_hashes(table_name, all_hashes)
        if sync_mode in _WATERMARK_MODES:
            if extracted.get("max_watermark") is not None:
                self.cache.set_last_watermark(table_name, extracted["max_watermark"])
            window = table.get("window_days")
            if window:
                self.cache.prune_stale_row_hashes(table_name, int(window) + 30)
        else:
            self.cache.mark_full_sync(table_name)
            current_pks = {
                SyncRuntimeOrchestrator._pk_value(row, pk_cols) for row in rows
            }
            self.cache.prune_missing_row_hashes(table_name, current_pks)
        self.cache.log_execution(execution_id, table_name, examined,
                                 len(changed_rows), len(changed_rows), skipped)

        summary = {
            "table_name": table_name, "sync_mode": table.get("sync_mode"),
            "status": "COMPLETED", "error_message": None,
            "examined": examined, "changed": len(changed_rows),
            "uploaded": len(changed_rows), "skipped": skipped,
            "chunk_count": len(chunks),
        }
        return summary, payload_chunks


def _sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()
