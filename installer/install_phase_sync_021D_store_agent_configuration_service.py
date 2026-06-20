# SYNC-021D Store Agent Configuration Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021D_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

service_code = """
from store_agent.store_agent_config_client import StoreAgentConfigClient
from store_agent.store_agent_config_contract import StoreAgentConfigContract

class StoreAgentConfigurationService:

    def get_runtime_config(self, url):

        config = StoreAgentConfigClient().get_config(url)

        for field in StoreAgentConfigContract.REQUIRED_FIELDS:
            if field not in config:
                raise ValueError(f"Missing configuration field: {field}")

        return config
"""

test_code = """
from store_agent.store_agent_config_contract import StoreAgentConfigContract

def test_contract_has_required_fields():
    assert len(StoreAgentConfigContract.REQUIRED_FIELDS) > 0
"""

write_file(
    ROOT / "store_agent" / "store_agent_configuration_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_store_agent_configuration_service.py",
    test_code
)

print("SYNC-021D INSTALL COMPLETE")
