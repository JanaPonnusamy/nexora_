# SYNC-022L Store Password Persistence Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022L_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = '''
from store_agent.store_password_repository_update import (
    StorePasswordRepositoryUpdate
)

class StorePasswordPersistenceService:

    def create_update_request(
        self,
        store_id,
        encrypted_password
    ):
        return (
            StorePasswordRepositoryUpdate()
            .build_update_command(
                store_id,
                encrypted_password
            )
        )
'''
test_code = '''
from store_agent.store_password_persistence_service import (
    StorePasswordPersistenceService
)

def test_persistence_service_exists():

    service = StorePasswordPersistenceService()

    sql, params = service.create_update_request(
        "STORE001",
        b"encrypted"
    )

    assert "UPDATE dbo.stores" in sql
'''
write_file(
    ROOT / "store_agent" / "store_password_persistence_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_store_password_persistence_service.py",
    test_code
)

print("SYNC-022L INSTALL COMPLETE")
