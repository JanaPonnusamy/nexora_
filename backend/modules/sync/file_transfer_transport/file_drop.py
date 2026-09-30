"""File-drop receiver transport: the HO half of store_agent/file_transfer/
file_drop_transport.py's layout::

    <root>/inbox/<store_id>/<package>.zip
    <root>/inbox/<store_id>/processed/<package>.zip   after successful import
    <root>/inbox/<store_id>/quarantine/<package>.zip  after rejection
    <root>/results/<store_id>/<result>.json
"""
import shutil
import tempfile
from pathlib import Path

from modules.sync.file_transfer_transport.base import ReceiverTransport


class FileDropReceiverTransport(ReceiverTransport):
    def __init__(self, root):
        self.root = Path(root)
        (self.root / "inbox").mkdir(parents=True, exist_ok=True)
        (self.root / "results").mkdir(parents=True, exist_ok=True)

    def list_incoming(self):
        """Returns TEMP COPIES, never the live inbox path -- the caller is
        free to delete every returned local_temp_path unconditionally once
        done with it (same contract SFTP/email give). The original inbox
        file is only ever touched by archive_incoming(); a package left
        un-archived (FAILED, retryable) is picked up again next tick."""
        inbox = self.root / "inbox"
        out = []
        if not inbox.is_dir():
            return out
        for store_dir in sorted(inbox.iterdir()):
            if not store_dir.is_dir():
                continue
            for pkg in sorted(store_dir.iterdir()):
                if pkg.is_file() and pkg.suffix == ".zip":
                    tmp = tempfile.NamedTemporaryFile(
                        prefix="nexora_pkg_", suffix=".zip", delete=False
                    )
                    tmp.close()
                    shutil.copy2(str(pkg), tmp.name)
                    out.append((store_dir.name + "/" + pkg.name, tmp.name))
        return out

    def archive_incoming(self, remote_name, success):
        store_id, filename = remote_name.split("/", 1)
        src = self.root / "inbox" / store_id / filename
        if not src.exists():
            return
        dest_dir = self.root / "inbox" / store_id / ("processed" if success else "quarantine")
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest_dir / filename))

    def send_result(self, store_id, result_filename, local_path):
        dest_dir = self.root / "results" / str(store_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / result_filename
        tmp = dest_dir / (result_filename + ".part")
        shutil.copy2(local_path, tmp)
        tmp.replace(dest)
