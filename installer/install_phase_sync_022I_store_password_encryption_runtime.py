# SYNC-022I Store Password Encryption Runtime Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022I_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

runtime_code = """
from store_agent.fernet_key_service import FernetKeyService
from backend.services.store_crypto_service import StoreCryptoService

class StorePasswordEncryptionRuntime:

    def encrypt_password(self, password):

        key_service = FernetKeyService()

        if key_service.key_exists():
            key = key_service.load_key()
        else:
            key = key_service.generate_key()
            key_service.save_key(key)

        return StoreCryptoService.encrypt_password(
            password,
            key
        )
"""

test_code = """
from store_agent.store_password_encryption_runtime import (
    StorePasswordEncryptionRuntime
)

def test_password_encryption_runtime_exists():

    runtime = StorePasswordEncryptionRuntime()

    assert runtime is not None
"""

write_file(
    ROOT / "store_agent" / "store_password_encryption_runtime.py",
    runtime_code
)

write_file(
    ROOT / "tests" / "test_store_password_encryption_runtime.py",
    test_code
)

print("SYNC-022I INSTALL COMPLETE")
