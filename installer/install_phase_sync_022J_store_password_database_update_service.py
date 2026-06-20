# SYNC-022J Store Password Database Update Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022J_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = """
class StorePasswordDatabaseUpdateService:

    def build_update_payload(
        self,
        store_id,
        encrypted_password
    ):

        return {
            "store_id": store_id,
            "password_encrypted": encrypted_password
        }
"""

test_code = """
from store_agent.store_password_database_update_service import (
    StorePasswordDatabaseUpdateService
)

def test_update_service_exists():

    service = StorePasswordDatabaseUpdateService()

    payload = service.build_update_payload(
        "STORE001",
        b"encrypted"
    )

    assert payload["store_id"] == "STORE001"
"""

write_file(
    ROOT / "store_agent" / "store_password_database_update_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_store_password_database_update_service.py",
    test_code
)

print("SYNC-022J INSTALL COMPLETE")
