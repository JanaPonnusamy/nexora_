# SYNC-022K Store Password Repository Update Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022K_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

repo_code = '''
class StorePasswordRepositoryUpdate:

    def build_update_command(
        self,
        store_id,
        encrypted_password
    ):

        sql = """
        UPDATE dbo.stores
        SET
            password_encrypted = ?,
            updated_at = GETDATE()
        WHERE
            store_id = ?
        """

        params = (
            encrypted_password,
            store_id
        )

        return sql, params
'''
test_code = '''
from store_agent.store_password_repository_update import (
    StorePasswordRepositoryUpdate
)

def test_build_update_command():

    repo = StorePasswordRepositoryUpdate()

    sql, params = repo.build_update_command(
        "STORE001",
        b"abc"
    )

    assert "UPDATE dbo.stores" in sql
    assert params[1] == "STORE001"
'''
write_file(
    ROOT / "store_agent" / "store_password_repository_update.py",
    repo_code
)

write_file(
    ROOT / "tests" / "test_store_password_repository_update.py",
    test_code
)

print("SYNC-022K INSTALL COMPLETE")
