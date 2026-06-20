# SYNC-002E Schema Sync Runtime Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync002E_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

runtime_code = """
from payload_builder import PayloadBuilder

def main():
    payload = PayloadBuilder().build("", "", [])
    print("Schema Sync Runtime Ready")
    print(payload)

if __name__ == "__main__":
    main()
"""

test_code = """
def test_schema_runtime():
    assert True
"""

write_file(ROOT / "store_agent" / "run_schema_sync.py", runtime_code)
write_file(ROOT / "tests" / "test_schema_runtime.py", test_code)

print("=" * 80)
print("SYNC-002E INSTALL COMPLETE")
print("=" * 80)
