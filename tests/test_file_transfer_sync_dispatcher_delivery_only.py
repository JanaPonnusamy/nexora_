"""FileTransferSyncDispatcher.run_delivery_only() -- the Phase 2 extraction
seam: sends the outbox + processes ACKs WITHOUT touching self.orchestrator
(which may be None), so the standalone NexoraMailTransfer process never
needs a SQL connection or the package-building engine, only the shared
SQLite outbox + a sender transport.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from store_agent.file_transfer.file_drop_transport import FileDropSenderTransport
from store_agent.file_transfer.outbox import FileTransferOutbox
from store_agent.file_transfer.sync_dispatcher import FileTransferSyncDispatcher
from store_agent.services.sqlite_cache_service import SqliteCacheService


class _ExplodingOrchestrator:
    def run_cycle(self):
        raise AssertionError(
            "run_delivery_only() must never call orchestrator.run_cycle() -- "
            "package building stays in the main agent process"
        )


def _make(tmp_dir):
    db_path = os.path.join(tmp_dir, "cache.db")
    cache = SqliteCacheService(db_path=db_path, store_id="STORE-1")
    outbox = FileTransferOutbox(cache, os.path.join(tmp_dir, "outbox"))
    sender = FileDropSenderTransport(os.path.join(tmp_dir, "transport_root"), store_id="STORE-1")
    return cache, outbox, sender


def test_run_delivery_only_never_touches_orchestrator_none():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox, sender = _make(tmp)
        dispatcher = FileTransferSyncDispatcher(None, outbox, sender)
        result = dispatcher.run_delivery_only()  # must not raise (no orchestrator at all)
        assert result == {"acks_processed": 0, "send": {"sent": 0, "failed": 0}}


def test_run_delivery_only_never_touches_orchestrator_even_if_provided():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox, sender = _make(tmp)
        dispatcher = FileTransferSyncDispatcher(_ExplodingOrchestrator(), outbox, sender)
        dispatcher.run_delivery_only()  # would raise AssertionError if orchestrator were touched


def test_run_delivery_only_sends_pending_and_processes_ack():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox, sender = _make(tmp)
        zip_path = os.path.join(str(outbox.pending_dir), "pkg1.zip")
        with open(zip_path, "wb") as fh:
            fh.write(b"zip-bytes")
        outbox.enqueue("pkg1", "exec1", zip_path, "deadbeef", 10, 1)

        dispatcher = FileTransferSyncDispatcher(None, outbox, sender)
        result = dispatcher.run_delivery_only()
        assert result["send"] == {"sent": 1, "failed": 0}
        assert cache.get_package("pkg1")["status"] == "SENT"

        # HO "publishes" a result back via the file-drop results folder.
        result_dir = os.path.join(tmp, "transport_root", "results", "STORE-1")
        os.makedirs(result_dir, exist_ok=True)
        with open(os.path.join(result_dir, "pkg1.json"), "w", encoding="utf-8") as fh:
            json.dump({"package_id": "pkg1", "status": "IMPORTED"}, fh)

        result2 = dispatcher.run_delivery_only()
        assert result2["acks_processed"] == 1
        assert cache.get_package("pkg1")["status"] == "ACKNOWLEDGED"
