"""FileDropSenderTransport -- pure filesystem round trip, no network."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from store_agent.file_transfer.file_drop_transport import FileDropSenderTransport
from store_agent.file_transfer.transport_factory import build_sender_transport


def test_upload_lands_in_store_scoped_inbox():
    with tempfile.TemporaryDirectory() as root:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as pkg:
            pkg.write(b"fake zip bytes")
            pkg_path = pkg.name
        try:
            transport = FileDropSenderTransport(root, store_id="STORE-1")
            transport.upload(pkg_path, "pkg1.zip")
            expected = os.path.join(root, "inbox", "STORE-1", "pkg1.zip")
            assert os.path.isfile(expected)
            with open(expected, "rb") as fh:
                assert fh.read() == b"fake zip bytes"
        finally:
            os.remove(pkg_path)


def test_list_and_remove_results_round_trip():
    with tempfile.TemporaryDirectory() as root:
        transport = FileDropSenderTransport(root, store_id="STORE-1")
        result_dir = os.path.join(root, "results", "STORE-1")
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, "pkg1.json")
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump({"package_id": "pkg1", "status": "IMPORTED"}, fh)

        results = transport.list_results()
        assert results == [("pkg1.json", result_path)]

        transport.remove_result("pkg1.json")
        assert not os.path.exists(result_path)
        processed = os.path.join(result_dir, "processed", "pkg1.json")
        assert os.path.isfile(processed)
        # Removed result is never returned again.
        assert transport.list_results() == []


def test_factory_rejects_unknown_mode():
    try:
        build_sender_transport({"mode": "CARRIER_PIGEON"}, store_id="STORE-1")
        assert False, "expected ValueError"
    except ValueError as ex:
        assert "CARRIER_PIGEON" in str(ex)


def test_factory_requires_root_for_file_drop():
    try:
        build_sender_transport({"mode": "FILE_DROP", "file_drop": {}}, store_id="STORE-1")
        assert False, "expected ValueError"
    except ValueError as ex:
        assert "root" in str(ex)
