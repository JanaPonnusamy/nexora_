"""FileTransferOutbox + SqliteCacheService package tracking -- SQLite only,
no SQL Server / network required."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from store_agent.services.sqlite_cache_service import SqliteCacheService
from store_agent.file_transfer.outbox import FileTransferOutbox


def _make(tmp_dir):
    db_path = os.path.join(tmp_dir, "cache.db")
    cache = SqliteCacheService(db_path=db_path, store_id="STORE-1")
    outbox = FileTransferOutbox(cache, os.path.join(tmp_dir, "outbox"))
    return cache, outbox


def _touch(path):
    with open(path, "wb") as fh:
        fh.write(b"zip-bytes")


def test_enqueue_registers_created_package():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox = _make(tmp)
        zip_path = os.path.join(str(outbox.pending_dir), "pkg1.zip")
        _touch(zip_path)

        outbox.enqueue("pkg1", "exec1", zip_path, "deadbeef", 10, 1)

        pkg = cache.get_package("pkg1")
        assert pkg["status"] == "CREATED"
        assert pkg["checksum"] == "deadbeef"
        assert outbox.due_for_send() and outbox.due_for_send()[0]["package_id"] == "pkg1"


def test_send_lifecycle_moves_between_folders():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox = _make(tmp)
        zip_path = os.path.join(str(outbox.pending_dir), "pkg1.zip")
        _touch(zip_path)
        outbox.enqueue("pkg1", "exec1", zip_path, "deadbeef", 10, 1)

        sending_path = outbox.mark_sending("pkg1", zip_path)
        assert os.path.isfile(sending_path)
        assert cache.get_package("pkg1")["status"] == "SENDING"

        sent_path = outbox.mark_sent("pkg1", sending_path)
        assert os.path.isfile(sent_path)
        pkg = cache.get_package("pkg1")
        assert pkg["status"] == "SENT"
        assert pkg["sent_on"] is not None

        outbox.mark_acknowledged("pkg1", {"status": "IMPORTED"})
        assert cache.get_package("pkg1")["status"] == "ACKNOWLEDGED"


def test_failed_send_is_retried_via_due_for_send():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox = _make(tmp)
        zip_path = os.path.join(str(outbox.pending_dir), "pkg1.zip")
        _touch(zip_path)
        outbox.enqueue("pkg1", "exec1", zip_path, "deadbeef", 10, 1)

        sending_path = outbox.mark_sending("pkg1", zip_path)
        outbox.mark_failed("pkg1", sending_path, "transport unreachable")

        pkg = cache.get_package("pkg1")
        assert pkg["status"] == "FAILED"
        assert pkg["attempts"] == 1
        assert pkg["last_error"] == "transport unreachable"

        due = outbox.due_for_send()
        assert [p["package_id"] for p in due] == ["pkg1"]


def test_negative_ack_result_marks_failed_not_acknowledged():
    with tempfile.TemporaryDirectory() as tmp:
        cache, outbox = _make(tmp)
        zip_path = os.path.join(str(outbox.pending_dir), "pkg1.zip")
        _touch(zip_path)
        outbox.enqueue("pkg1", "exec1", zip_path, "deadbeef", 10, 1)
        outbox.mark_sent("pkg1", zip_path)

        outbox.mark_acknowledged("pkg1", {"status": "REJECTED", "error_message": "bad checksum"})

        pkg = cache.get_package("pkg1")
        assert pkg["status"] == "FAILED"
        assert pkg["last_error"] == "bad checksum"
