"""PackageBuilder -- pure filesystem/zip logic, no database or network."""
import hashlib
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from store_agent.file_transfer.package_builder import PackageBuilder


def _table_summary(name="Products", chunks=1, changed=2):
    return {
        "table_name": name, "sync_mode": "UPSERT", "status": "COMPLETED",
        "error_message": None, "examined": 10, "changed": changed,
        "uploaded": changed, "skipped": 10 - changed, "chunk_count": chunks,
    }


def test_build_produces_manifest_checksums_and_payload():
    builder = PackageBuilder(store_id="STORE-1", tenant_id="TENANT-1", agent_version="9.9.9")
    execution_id = "exec-123"
    chunks = [
        ("Products", 1, {
            "execution_id": execution_id, "table_name": "Products", "chunk_no": 1,
            "rows": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
            "total_rows": 2, "sync_type": "UPSERT",
        }),
    ]
    with tempfile.TemporaryDirectory() as out_dir:
        zip_path, manifest = builder.build(
            execution_id, [_table_summary()], chunks, out_dir=out_dir, seq=1
        )

        assert os.path.isfile(zip_path)
        assert manifest["package_id"] == execution_id
        assert manifest["store_id"] == "STORE-1"
        assert manifest["tenant_id"] == "TENANT-1"
        assert manifest["sync_mode"] == "FILE_TRANSFER"
        assert manifest["totals"]["total_rows"] == 2
        assert manifest["totals"]["total_chunks"] == 1
        assert manifest["payload_files"] == ["payload/Products__1.json"]

        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            assert names == {"manifest.json", "checksums.json", "payload/Products__1.json"}

            checksums = json.loads(zf.read("checksums.json"))
            for rel, expected in checksums.items():
                actual = hashlib.sha256(zf.read(rel)).hexdigest()
                assert actual == expected, "checksum mismatch for %s" % rel

            payload = json.loads(zf.read("payload/Products__1.json"))
            assert payload["rows"] == chunks[0][2]["rows"]


def test_build_with_no_changes_still_produces_valid_manifest():
    builder = PackageBuilder(store_id="STORE-2", tenant_id=None)
    with tempfile.TemporaryDirectory() as out_dir:
        zip_path, manifest = builder.build(
            "exec-456", [], [], out_dir=out_dir, seq=7
        )
        assert manifest["totals"]["total_rows"] == 0
        assert manifest["payload_files"] == []
        with zipfile.ZipFile(zip_path) as zf:
            assert set(zf.namelist()) == {"manifest.json", "checksums.json"}


def test_zip_filename_is_unique_per_sequence():
    builder = PackageBuilder(store_id="STORE-3", tenant_id=None)
    with tempfile.TemporaryDirectory() as out_dir:
        zip_path_1, _ = builder.build("exec-a", [], [], out_dir=out_dir, seq=1)
        zip_path_2, _ = builder.build("exec-b", [], [], out_dir=out_dir, seq=2)
        assert zip_path_1 != zip_path_2
        assert os.path.isfile(zip_path_1)
        assert os.path.isfile(zip_path_2)
