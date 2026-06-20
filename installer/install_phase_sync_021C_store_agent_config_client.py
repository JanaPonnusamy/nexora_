# SYNC-021C Store Agent Config Client Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021C_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

client_code = """
import requests

class StoreAgentConfigClient:

    def get_config(self, url):

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        return response.json()
"""

test_code = """
from store_agent.store_agent_config_client import StoreAgentConfigClient

def test_client_exists():
    client = StoreAgentConfigClient()
    assert client is not None
"""

write_file(
    ROOT / "store_agent" / "store_agent_config_client.py",
    client_code
)

write_file(
    ROOT / "tests" / "test_store_agent_config_client.py",
    test_code
)

print("SYNC-021C INSTALL COMPLETE")
