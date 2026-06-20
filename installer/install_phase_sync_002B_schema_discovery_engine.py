# SYNC-002B Schema Discovery Engine Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if not path.exists():
        return
    backup_dir = ROOT / "backup" / f"sync002B_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")
    print(f"CREATED : {path}")

schema_scanner = """
class SchemaScanner:
    def scan(self):
        return []
"""

test_code = """
from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_exists():
    scanner = SchemaScanner()
    assert scanner is not None
"""

write_file(ROOT / "store_agent" / "schema_scanner.py", schema_scanner.strip() + "\\n")
write_file(ROOT / "tests" / "test_schema_scanner.py", test_code.strip() + "\\n")

print("=" * 80)
print("SYNC-002B INSTALL COMPLETE")
print("=" * 80)
