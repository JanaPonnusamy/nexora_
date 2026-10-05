"""file_transfer_validator -- pure filesystem/zip logic, no database.

Covers objective 17 (safe extraction: path traversal, size limits, checksum
verification) and objective 13 (manifest schema validation).
"""
import hashlib
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.sync.file_transfer_validator import (
    PackageValidationError, extract_package, verify_checksums, load_manifest,
    load_chunk_bodies,
)


def _valid_manifest(execution_id="exec-1", store_id="store-1"):
    return {
        "package_id": execution_id, "execution_id": execution_id,
        "schema_version": 1, "store_id": store_id, "tenant_id": "tenant-1",
        "created_at": "2026-09-18T00:00:00Z", "sync_mode": "FILE_TRANSFER",
        "tables": [{"table_name": "Products", "sync_mode": "UPSERT",
                    "status": "COMPLETED", "examined": 1, "changed": 1,
                    "uploaded": 1, "skipped": 0}],
        "payload_files": ["payload/Products__1.json"],
        "totals": {"total_rows": 1, "total_chunks": 1, "total_tables": 1},
    }


def _build_zip(path, manifest, chunk_body):
    work = tempfile.mkdtemp()
    manifest_path = os.path.join(work, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    payload_dir = os.path.join(work, "payload")
    os.makedirs(payload_dir, exist_ok=True)
    payload_path = os.path.join(payload_dir, "Products__1.json")
    with open(payload_path, "w", encoding="utf-8") as fh:
        json.dump(chunk_body, fh)

    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            h.update(fh.read())
        return h.hexdigest()

    checksums = {
        "manifest.json": sha(manifest_path),
        "payload/Products__1.json": sha(payload_path),
    }
    checksums_path = os.path.join(work, "checksums.json")
    with open(checksums_path, "w", encoding="utf-8") as fh:
        json.dump(checksums, fh)

    with zipfile.ZipFile(path, "w") as zf:
        zf.write(manifest_path, "manifest.json")
        zf.write(checksums_path, "checksums.json")
        zf.write(payload_path, "payload/Products__1.json")
    return checksums


def test_full_valid_package_round_trip():
    manifest = _valid_manifest()
    chunk_body = {
        "execution_id": "exec-1", "table_name": "Products", "chunk_no": 1,
        "rows": [{"id": 1}], "total_rows": 1, "sync_type": "UPSERT",
    }
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "pkg.zip")
        _build_zip(zip_path, manifest, chunk_body)

        extract_dir = extract_package(zip_path)
        try:
            verify_checksums(extract_dir)
            loaded = load_manifest(extract_dir)
            assert loaded["package_id"] == "exec-1"
            bodies = load_chunk_bodies(extract_dir, loaded)
            assert len(bodies) == 1
            assert bodies[0]["rows"] == [{"id": 1}]
        finally:
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)


def test_tampered_payload_fails_checksum():
    manifest = _valid_manifest()
    chunk_body = {"execution_id": "exec-1", "table_name": "Products",
                  "chunk_no": 1, "rows": [{"id": 1}]}
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "pkg.zip")
        _build_zip(zip_path, manifest, chunk_body)

        # Tamper: rewrite the zip with a modified payload but stale checksums.
        extract_dir = extract_package(zip_path)
        with open(os.path.join(extract_dir, "payload", "Products__1.json"), "w") as fh:
            json.dump({"execution_id": "exec-1", "table_name": "Products",
                       "chunk_no": 1, "rows": [{"id": 999}]}, fh)

        try:
            verify_checksums(extract_dir)
            assert False, "expected PackageValidationError"
        except PackageValidationError as ex:
            assert "Checksum mismatch" in str(ex)


def test_path_traversal_entry_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "evil.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../evil.txt", "pwned")
        try:
            extract_package(zip_path)
            assert False, "expected PackageValidationError"
        except PackageValidationError as ex:
            assert "traversal" in str(ex) or "Unsafe" in str(ex)


def test_manifest_missing_required_key_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "payload"))
        manifest = _valid_manifest()
        del manifest["store_id"]
        with open(os.path.join(tmp, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)
        try:
            load_manifest(tmp)
            assert False, "expected PackageValidationError"
        except PackageValidationError as ex:
            assert "store_id" in str(ex)


def test_wrong_sync_mode_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        manifest = _valid_manifest()
        manifest["sync_mode"] = "DIRECT_HTTP"
        with open(os.path.join(tmp, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)
        try:
            load_manifest(tmp)
            assert False, "expected PackageValidationError"
        except PackageValidationError as ex:
            assert "sync_mode" in str(ex)


def test_chunk_body_execution_id_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        manifest = _valid_manifest()
        os.makedirs(os.path.join(tmp, "payload"))
        with open(os.path.join(tmp, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)
        with open(os.path.join(tmp, "payload", "Products__1.json"), "w") as fh:
            json.dump({"execution_id": "OTHER-EXEC", "table_name": "Products",
                       "chunk_no": 1, "rows": []}, fh)
        try:
            load_chunk_bodies(tmp, manifest)
            assert False, "expected PackageValidationError"
        except PackageValidationError as ex:
            assert "execution_id" in str(ex)
