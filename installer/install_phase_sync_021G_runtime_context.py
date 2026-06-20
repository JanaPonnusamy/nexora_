# SYNC-021G Store Agent Runtime Context Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021G_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

runtime_context_code = """
class StoreAgentRuntimeContext:

    def __init__(self, runtime_config):

        self.store_id = runtime_config.get("store_id")
        self.sql_server = runtime_config.get("sql_server")
        self.database_name = runtime_config.get("database_name")
        self.sql_username = runtime_config.get("sql_username")
        self.sql_password = runtime_config.get("sql_password")
        self.ho_api_url = runtime_config.get("ho_api_url")

    def to_dict(self):

        return {
            "store_id": self.store_id,
            "sql_server": self.sql_server,
            "database_name": self.database_name,
            "sql_username": self.sql_username,
            "sql_password": self.sql_password,
            "ho_api_url": self.ho_api_url
        }
"""

test_code = """
from store_agent.runtime_context import StoreAgentRuntimeContext

def test_runtime_context_exists():

    ctx = StoreAgentRuntimeContext({})

    assert ctx is not None
"""

write_file(
    ROOT / "store_agent" / "runtime_context.py",
    runtime_context_code
)

write_file(
    ROOT / "tests" / "test_runtime_context.py",
    test_code
)

print("SYNC-021G INSTALL COMPLETE")
