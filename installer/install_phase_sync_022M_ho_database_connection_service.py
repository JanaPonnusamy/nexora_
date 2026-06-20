# SYNC-022M HO Database Connection Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022M_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = '''
class HoDatabaseConnectionService:

    def build_update_execution(
        self,
        sql,
        params
    ):
        return {
            "sql": sql,
            "params": params
        }
'''
test_code = '''
from store_agent.ho_database_connection_service import (
    HoDatabaseConnectionService
)

def test_ho_database_connection_service():

    service = HoDatabaseConnectionService()

    result = service.build_update_execution(
        "UPDATE dbo.stores",
        ("abc", "store1")
    )

    assert result["sql"] == "UPDATE dbo.stores"
'''
write_file(
    ROOT / "store_agent" / "ho_database_connection_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_ho_database_connection_service.py",
    test_code
)

print("SYNC-022M INSTALL COMPLETE")
