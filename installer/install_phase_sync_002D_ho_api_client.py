# SYNC-002D HO API CLIENT Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync002D_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

sync_client = """
import requests

class SyncClient:

    def post_schema(self, url, payload):
        response = requests.post(url, json=payload, timeout=60)
        return response.status_code
"""

test_code = """
from store_agent.sync_client import SyncClient

def test_sync_client_exists():
    client = SyncClient()
    assert client is not None
"""

write_file(ROOT / "store_agent" / "sync_client.py", sync_client)
write_file(ROOT / "tests" / "test_sync_client.py", test_code)

print("=" * 80)
print("SYNC-002D INSTALL COMPLETE")
print("=" * 80)
