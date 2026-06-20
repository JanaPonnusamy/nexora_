# SYNC-021B Store Agent Config Contract Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021B_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

contract_code = """
class StoreAgentConfigContract:

    REQUIRED_FIELDS = [
        "store_id",
        "server_name",
        "database_name",
        "sql_username",
        "sql_password",
        "ho_api_url"
    ]
"""

test_code = """
from store_agent.store_agent_config_contract import StoreAgentConfigContract

def test_contract_fields():
    assert "store_id" in StoreAgentConfigContract.REQUIRED_FIELDS
    assert "ho_api_url" in StoreAgentConfigContract.REQUIRED_FIELDS
"""

write_file(
    ROOT / "store_agent" / "store_agent_config_contract.py",
    contract_code
)

write_file(
    ROOT / "tests" / "test_store_agent_config_contract.py",
    test_code
)

print("SYNC-021B INSTALL COMPLETE")
