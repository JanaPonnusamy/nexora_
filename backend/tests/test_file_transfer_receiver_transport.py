"""FileDropReceiverTransport -- pure filesystem round trip, no network.

Also proves store_agent's sender and this receiver agree on the same
on-disk layout without either side importing the other (they are separate
deployables in production): both place packages under
<root>/inbox/<store_id>/<file>.zip and results under
<root>/results/<store_id>/<file>.json.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.sync.file_transfer_transport.file_drop import FileDropReceiverTransport
from modules.sync.file_transfer_transport.factory import build_receiver_transport


def test_list_incoming_finds_packages_across_stores():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "inbox", "store-a"))
        os.makedirs(os.path.join(root, "inbox", "store-b"))
        with open(os.path.join(root, "inbox", "store-a", "pkg1.zip"), "wb") as fh:
            fh.write(b"zip-a")
        with open(os.path.join(root, "inbox", "store-b", "pkg2.zip"), "wb") as fh:
            fh.write(b"zip-b")

        transport = FileDropReceiverTransport(root)
        found = transport.list_incoming()
        names = sorted(name for name, _ in found)
        assert names == ["store-a/pkg1.zip", "store-b/pkg2.zip"]

        # Returned paths are temp copies -- deleting them must not touch the
        # original inbox files (the caller always deletes its local copy).
        for _, local_path in found:
            os.remove(local_path)
        assert os.path.isfile(os.path.join(root, "inbox", "store-a", "pkg1.zip"))


def test_archive_incoming_moves_to_processed_on_success():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "inbox", "store-a"))
        pkg_path = os.path.join(root, "inbox", "store-a", "pkg1.zip")
        with open(pkg_path, "wb") as fh:
            fh.write(b"zip-a")

        transport = FileDropReceiverTransport(root)
        transport.archive_incoming("store-a/pkg1.zip", success=True)

        assert not os.path.exists(pkg_path)
        assert os.path.isfile(os.path.join(root, "inbox", "store-a", "processed", "pkg1.zip"))


def test_archive_incoming_moves_to_quarantine_on_failure():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "inbox", "store-a"))
        pkg_path = os.path.join(root, "inbox", "store-a", "pkg1.zip")
        with open(pkg_path, "wb") as fh:
            fh.write(b"zip-a")

        transport = FileDropReceiverTransport(root)
        transport.archive_incoming("store-a/pkg1.zip", success=False)

        assert os.path.isfile(os.path.join(root, "inbox", "store-a", "quarantine", "pkg1.zip"))


def test_send_result_lands_where_store_agent_expects_it():
    with tempfile.TemporaryDirectory() as root:
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            json.dump({"package_id": "pkg1", "status": "IMPORTED"}, tmp)
            local_path = tmp.name
        try:
            transport = FileDropReceiverTransport(root)
            transport.send_result("store-a", "pkg1.json", local_path)
            expected = os.path.join(root, "results", "store-a", "pkg1.json")
            assert os.path.isfile(expected)
            with open(expected) as fh:
                assert json.load(fh)["status"] == "IMPORTED"
        finally:
            os.remove(local_path)


def test_factory_rejects_unknown_mode():
    try:
        build_receiver_transport({"mode": "CARRIER_PIGEON"})
        assert False, "expected ValueError"
    except ValueError as ex:
        assert "CARRIER_PIGEON" in str(ex)
