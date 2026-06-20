# SYNC-022D Store Agent Config Decryption Service Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022D_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

service_code = """
from backend.services.store_crypto_service import (
    StoreCryptoService
)

class StoreAgentConfigDecryptionService:

    def decrypt_password(
        self,
        encrypted_password,
        key
    ):
        return StoreCryptoService.decrypt_password(
            encrypted_password,
            key
        )
"""

test_code = """
from store_agent.store_agent_config_decryption_service import (
    StoreAgentConfigDecryptionService
)

def test_decryption_service_exists():
    service = StoreAgentConfigDecryptionService()
    assert service is not None
"""

write_file(
    ROOT / "store_agent" / "store_agent_config_decryption_service.py",
    service_code
)

write_file(
    ROOT / "tests" / "test_store_agent_config_decryption_service.py",
    test_code
)

print("SYNC-022D INSTALL COMPLETE")
