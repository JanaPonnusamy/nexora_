# SYNC-022A Store Crypto Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022A_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\\n", encoding="utf-8")

service_code = """
from cryptography.fernet import Fernet

class StoreCryptoService:

    @staticmethod
    def generate_key():
        return Fernet.generate_key()

    @staticmethod
    def encrypt_password(password: str, key: bytes) -> bytes:
        return Fernet(key).encrypt(password.encode("utf-8"))

    @staticmethod
    def decrypt_password(encrypted_password: bytes, key: bytes) -> str:
        return Fernet(key).decrypt(encrypted_password).decode("utf-8")
"""

test_code = """
from services.store_crypto_service import StoreCryptoService

def test_encrypt_decrypt_password():
    key = StoreCryptoService.generate_key()
    encrypted = StoreCryptoService.encrypt_password("Admin123", key)

    assert encrypted != b"Admin123"

    decrypted = StoreCryptoService.decrypt_password(
        encrypted,
        key
    )

    assert decrypted == "Admin123"
"""

write_file(
    ROOT / "backend" / "services" / "store_crypto_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_store_crypto_service.py",
    test_code
)

print("SYNC-022A INSTALL COMPLETE")
