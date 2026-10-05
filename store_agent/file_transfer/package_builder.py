"""Builds the single ZIP package transferred per FILE_TRANSFER sync cycle.

Package layout::

    manifest.json     package/execution identity, table summaries, file list
    checksums.json     sha256 of every other file in the package (self-check,
                       independent of whatever integrity the transport gives)
    payload/<table>__<chunk_no>.json
                       one file per (table, chunk); same JSON shape as the
                       existing DIRECT_HTTP chunk-upload body
                       ({execution_id, table_name, chunk_no, rows, ...}) so
                       HO's existing merge code (runtime_repository.upload_chunk)
                       can run unmodified against it.

Internal batching (many tables, many chunks) is fine -- ChunkBuilderService
still slices large tables into manageable pieces for the merge step on the
HO side. What matters for objective 9 ("no external chunking") is that only
ONE file -- the zip -- is ever handed to a Transport adapter.
"""
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

SCHEMA_VERSION = 1


class PackageBuilder:
    def __init__(self, store_id, tenant_id, agent_version="unknown"):
        self.store_id = store_id
        self.tenant_id = tenant_id
        self.agent_version = agent_version

    def build(self, execution_id, table_summaries, payload_chunks, out_dir, seq):
        """payload_chunks: iterable of (table_name, chunk_no, chunk_body dict).
        table_summaries: per-table dicts (table_name, sync_mode, examined,
        changed, uploaded, skipped, status, error_message, chunk_count).
        Returns (zip_path, manifest_dict)."""
        work = tempfile.mkdtemp(prefix="nexora_pkg_")
        try:
            payload_dir = os.path.join(work, "payload")
            os.makedirs(payload_dir, exist_ok=True)

            payload_files = []
            total_rows = 0
            for table_name, chunk_no, body in payload_chunks:
                rel = "payload/%s__%d.json" % (_safe_name(table_name), chunk_no)
                with open(os.path.join(work, rel), "w", encoding="utf-8") as fh:
                    json.dump(body, fh, default=str)
                payload_files.append(rel)
                total_rows += len(body.get("rows") or [])

            manifest = {
                "package_id": execution_id,
                "execution_id": execution_id,
                "schema_version": SCHEMA_VERSION,
                "tenant_id": self.tenant_id,
                "store_id": self.store_id,
                "agent_version": self.agent_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sync_mode": "FILE_TRANSFER",
                "tables": table_summaries,
                "payload_files": payload_files,
                "totals": {
                    "total_rows": total_rows,
                    "total_chunks": len(payload_files),
                    "total_tables": len(table_summaries),
                },
            }
            manifest_path = os.path.join(work, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, default=str)

            checksums = {"manifest.json": _sha256_file(manifest_path)}
            for rel in payload_files:
                checksums[rel] = _sha256_file(os.path.join(work, rel))
            checksums_path = os.path.join(work, "checksums.json")
            with open(checksums_path, "w", encoding="utf-8") as fh:
                json.dump(checksums, fh)

            zip_name = "%s_%s_SYNC_%06d.zip" % (
                _safe_name(self.store_id),
                datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
                seq,
            )
            os.makedirs(out_dir, exist_ok=True)
            zip_path = os.path.join(out_dir, zip_name)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(manifest_path, "manifest.json")
                zf.write(checksums_path, "checksums.json")
                for rel in payload_files:
                    zf.write(os.path.join(work, rel), rel)

            return zip_path, manifest
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _safe_name(value):
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(value))


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()
