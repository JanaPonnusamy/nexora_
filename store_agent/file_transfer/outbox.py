"""Durable local outbox for FILE_TRANSFER packages.

SQLite (SqliteCacheService.file_sync_packages) is the single source of truth
for package status -- the same pattern sync_pending_chunks already uses as
the DIRECT_HTTP offline outbox. The pending/sending/sent/failed folders
mirror that status on disk purely for operator visibility (an operator can
`dir` the failed folder to see what needs attention); nothing reads the
folder layout back to decide state -- the database does.

States: CREATED -> SENDING -> SENT -> ACKNOWLEDGED, or -> FAILED at any point
(retried from FAILED on the next cycle).
"""
import shutil
from pathlib import Path


class FileTransferOutbox:
    def __init__(self, cache, root_dir):
        self.cache = cache
        self.root = Path(root_dir)
        for sub in ("pending", "sending", "sent", "failed"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    @property
    def pending_dir(self):
        return self.root / "pending"

    def enqueue(self, package_id, execution_id, zip_path, checksum,
               total_rows, total_chunks):
        """Registers a freshly built package (already sitting in pending_dir)
        as CREATED and ready to send."""
        self.cache.queue_package(
            package_id, execution_id, str(zip_path), checksum,
            total_rows, total_chunks,
        )

    def due_for_send(self):
        """Packages that still need a transport attempt: never sent, or a
        previous attempt failed."""
        return (
            self.cache.get_packages_by_status("CREATED")
            + self.cache.get_packages_by_status("FAILED")
        )

    def mark_sending(self, package_id, zip_path):
        dest = self._move(zip_path, "sending")
        self.cache.set_package_status(package_id, "SENDING")
        return dest

    def mark_sent(self, package_id, zip_path):
        dest = self._move(zip_path, "sent")
        self.cache.set_package_status(package_id, "SENT")
        return dest

    def mark_failed(self, package_id, zip_path, error):
        dest = self._move(zip_path, "failed")
        self.cache.increment_package_attempt(package_id)
        self.cache.set_package_status(package_id, "FAILED", error=error)
        return dest

    def mark_acknowledged(self, package_id, result):
        self.cache.mark_package_acknowledged(package_id, result)

    def _move(self, current_path, sub):
        src = Path(current_path)
        if not src.exists():
            return str(src)
        dest = self.root / sub / src.name
        shutil.move(str(src), str(dest))
        return str(dest)
