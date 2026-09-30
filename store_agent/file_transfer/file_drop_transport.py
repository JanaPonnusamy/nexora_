"""File-drop transport (store-agent/sender side): a shared/mounted filesystem
path as the transfer channel. Works over any path Python can write to -- a
local folder (dev/test), a mapped network drive, or a UNC share reachable
without a domain trust (e.g. an internet-facing WebDAV/SMB gateway already
provisioned by IT).

Layout under the configured root (the HO-side receiver, a separate
deployable -- backend/modules/sync/file_transfer_transport/file_drop.py --
implements the other half of this same layout)::

    <root>/inbox/<store_id>/<package>.zip          store -> HO, waiting
    <root>/inbox/<store_id>/processed/<package>.zip   HO archived (imported)
    <root>/inbox/<store_id>/quarantine/<package>.zip  HO archived (rejected)
    <root>/results/<store_id>/<result>.json        HO -> store, waiting
    <root>/results/<store_id>/processed/<result>.json  store archived

This is the one transport that needs zero optional dependencies and zero
external service, so it is also what the test suite exercises end to end.
"""
import shutil
from pathlib import Path

from store_agent.file_transfer.transport_base import SenderTransport


class FileDropSenderTransport(SenderTransport):
    def __init__(self, root, store_id):
        self.root = Path(root)
        self.store_id = str(store_id)
        self.inbox_dir = self.root / "inbox" / self.store_id
        self.results_dir = self.root / "results" / self.store_id
        self.results_processed_dir = self.results_dir / "processed"
        for d in (self.inbox_dir, self.results_dir, self.results_processed_dir):
            d.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path, remote_name):
        dest = self.inbox_dir / remote_name
        tmp = self.inbox_dir / (remote_name + ".part")
        shutil.copy2(local_path, tmp)
        tmp.replace(dest)  # atomic within the same filesystem

    def list_results(self):
        if not self.results_dir.is_dir():
            return []
        return [
            (p.name, str(p))
            for p in sorted(self.results_dir.iterdir())
            if p.is_file() and p.suffix == ".json"
        ]

    def remove_result(self, remote_name):
        src = self.results_dir / remote_name
        if src.exists():
            shutil.move(str(src), str(self.results_processed_dir / remote_name))
