# SYNC-022E Store Agent Runtime SQL Connection Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022E_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = """
from store_agent.sql_connection_provider import (
    SqlConnectionProvider
)

class RuntimeSqlConnectionService:

    def connect(self, runtime_context):

        return (
            SqlConnectionProvider()
            .get_connection(runtime_context)
        )
"""

test_code = """
from store_agent.runtime_sql_connection_service import (
    RuntimeSqlConnectionService
)

def test_runtime_sql_connection_service_exists():
    service = RuntimeSqlConnectionService()
    assert service is not None
"""

write_file(
    ROOT / "store_agent" / "runtime_sql_connection_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_runtime_sql_connection_service.py",
    test_code
)

print("SYNC-022E INSTALL COMPLETE")
