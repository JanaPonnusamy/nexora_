# SYNC-022H Fernet Key Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022H_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = """
from pathlib import Path
from cryptography.fernet import Fernet

class FernetKeyService:

    KEY_FILE = Path(__file__).parent / "config" / "fernet.key"

    def generate_key(self):
        return Fernet.generate_key()

    def save_key(self, key):

        self.KEY_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.KEY_FILE.write_bytes(key)

    def load_key(self):

        return self.KEY_FILE.read_bytes()

    def key_exists(self):

        return self.KEY_FILE.exists()
"""

test_code = """
from store_agent.fernet_key_service import FernetKeyService

def test_fernet_key_service_exists():

    service = FernetKeyService()

    assert service is not None
"""

write_file(
    ROOT / "store_agent" / "fernet_key_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_fernet_key_service.py",
    test_code
)

print("SYNC-022H INSTALL COMPLETE")
