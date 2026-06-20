# SYNC-021E Runtime Configuration Loader Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021E_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

loader_code = """
from store_agent.store_agent_configuration_service import (
    StoreAgentConfigurationService
)

class RuntimeConfigurationLoader:

    def load(self, url):

        config = (
            StoreAgentConfigurationService()
            .get_runtime_config(url)
        )

        return {
            "sql_server": config.get("server_name"),
            "database_name": config.get("database_name"),
            "sql_username": config.get("sql_username"),
            "sql_password": config.get("sql_password"),
            "ho_api_url": config.get("ho_api_url"),
            "store_id": config.get("store_id")
        }
"""

test_code = """
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader

def test_loader_exists():
    loader = RuntimeConfigurationLoader()
    assert loader is not None
"""

write_file(
    ROOT / "store_agent" / "runtime_configuration_loader.py",
    loader_code
)

write_file(
    ROOT / "tests" / "test_runtime_configuration_loader.py",
    test_code
)

print("SYNC-021E INSTALL COMPLETE")
