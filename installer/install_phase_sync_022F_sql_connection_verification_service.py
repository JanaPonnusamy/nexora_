# SYNC-022F SQL Connection Verification Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022F_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = """
class SqlConnectionVerificationService:

    def verify(self, connection):

        cursor = connection.cursor()

        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]

        cursor.execute("SELECT DB_NAME()")
        database_name = cursor.fetchone()[0]

        return {
            "is_connected": True,
            "sql_version": version,
            "database_name": database_name
        }
"""

test_code = """
from store_agent.sql_connection_verification_service import (
    SqlConnectionVerificationService
)

def test_verification_service_exists():
    service = SqlConnectionVerificationService()
    assert service is not None
"""

write_file(
    ROOT / "store_agent" / "sql_connection_verification_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_sql_connection_verification_service.py",
    test_code
)

print("SYNC-022F INSTALL COMPLETE")
