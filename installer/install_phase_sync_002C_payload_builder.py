# SYNC-002C Payload Builder Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync002C_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

payload_builder = """
class PayloadBuilder:

    def build(self, store_id, database_name, tables):
        return {
            "store_id": store_id,
            "database_name": database_name,
            "tables": tables
        }
"""

test_code = """
from store_agent.payload_builder import PayloadBuilder

def test_payload_builder():
    builder = PayloadBuilder()

    payload = builder.build(
        "STORE-001",
        "PHARMACY_DB",
        []
    )

    assert payload["store_id"] == "STORE-001"
    assert payload["database_name"] == "PHARMACY_DB"
    assert isinstance(payload["tables"], list)
"""

write_file(ROOT / "store_agent" / "payload_builder.py", payload_builder)
write_file(ROOT / "tests" / "test_payload_builder.py", test_code)

print("=" * 80)
print("SYNC-002C INSTALL COMPLETE")
print("=" * 80)
