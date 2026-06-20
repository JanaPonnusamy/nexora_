# SYNC-008 INFORMATION_SCHEMA Table Discovery Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync008_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

scanner_code = '''
from store_agent.database import get_connection

class SchemaScanner:

    def get_tables(self):

        conn = get_connection()
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT TABLE_SCHEMA,TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
        ORDER BY TABLE_SCHEMA,TABLE_NAME
        """).fetchall()

        conn.close()

        return [
            {
                "schema_name": r[0],
                "table_name": r[1]
            }
            for r in rows
        ]
'''

test_code = '''
from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_get_tables():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_tables")
'''

write_file(ROOT / "store_agent" / "schema_scanner.py", scanner_code)
write_file(ROOT / "tests" / "test_table_discovery.py", test_code)

print("=" * 80)
print("SYNC-008 INSTALL COMPLETE")
print("=" * 80)
