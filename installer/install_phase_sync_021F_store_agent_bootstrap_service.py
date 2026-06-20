# SYNC-021F Store Agent Bootstrap Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021F_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

bootstrap_code = """
from store_agent.runtime_configuration_loader import (
    RuntimeConfigurationLoader
)

class StoreAgentBootstrapService:

    def bootstrap(self, config_url):

        runtime_config = (
            RuntimeConfigurationLoader()
            .load(config_url)
        )

        return {
            "status": "ready",
            "runtime_config": runtime_config
        }
"""

test_code = """
from store_agent.store_agent_bootstrap_service import (
    StoreAgentBootstrapService
)

def test_bootstrap_service_exists():
    service = StoreAgentBootstrapService()
    assert service is not None
"""

write_file(
    ROOT / "store_agent" / "store_agent_bootstrap_service.py",
    bootstrap_code
)

write_file(
    ROOT / "tests" / "test_store_agent_bootstrap_service.py",
    test_code
)

print("SYNC-021F INSTALL COMPLETE")
