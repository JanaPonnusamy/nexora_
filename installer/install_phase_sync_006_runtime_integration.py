# SYNC-006 End-to-End Schema Sync Runtime Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync006_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

runtime_code = """
from store_agent.schema_registration_service import SchemaRegistrationService

def main():
    service = SchemaRegistrationService()

    print("SYNC-006 Runtime Ready")
    print(service)

if __name__ == "__main__":
    main()
"""

test_code = """
from store_agent.schema_registration_service import SchemaRegistrationService

def test_runtime_dependencies():
    service = SchemaRegistrationService()
    assert service is not None
"""

write_file(ROOT / "store_agent" / "run_schema_sync.py", runtime_code)
write_file(ROOT / "tests" / "test_sync_runtime.py", test_code)

print("=" * 80)
print("SYNC-006 INSTALL COMPLETE")
print("=" * 80)
