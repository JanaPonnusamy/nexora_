# SYNC-022C Store Agent Config Download Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022C_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = """
import requests

class StoreAgentConfigDownloadService:

    def download(self, url):

        response = requests.get(url, timeout=30)

        response.raise_for_status()

        return response.json()
"""

test_code = """
from store_agent.store_agent_config_download_service import (
    StoreAgentConfigDownloadService
)

def test_download_service_exists():
    service = StoreAgentConfigDownloadService()
    assert service is not None
"""

write_file(
    ROOT / "store_agent" / "store_agent_config_download_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_store_agent_config_download_service.py",
    test_code
)

print("SYNC-022C INSTALL COMPLETE")
