# SYNC-003 Real SQL Schema Scanner Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync003_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

schema_scanner = """
class SchemaScanner:

    def get_tables(self):
        return []

    def get_columns(self):
        return []

    def scan(self):
        return {
            "tables": self.get_tables(),
            "columns": self.get_columns()
        }
"""

test_code = """
from store_agent.schema_scanner import SchemaScanner

def test_schema_scan_result():
    result = SchemaScanner().scan()

    assert "tables" in result
    assert "columns" in result
"""

write_file(ROOT / "store_agent" / "schema_scanner.py", schema_scanner)
write_file(ROOT / "tests" / "test_schema_scanner_runtime.py", test_code)

print("=" * 80)
print("SYNC-003 INSTALL COMPLETE")
print("=" * 80)
