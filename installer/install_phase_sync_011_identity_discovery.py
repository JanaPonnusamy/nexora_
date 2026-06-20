# SYNC-011 Identity Column Discovery Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync011_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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

    def get_identity_columns(self):

        conn = get_connection()
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            c.name AS column_name
        FROM sys.columns c
        INNER JOIN sys.tables t
            ON c.object_id = t.object_id
        INNER JOIN sys.schemas s
            ON t.schema_id = s.schema_id
        WHERE c.is_identity = 1
        ORDER BY s.name,t.name,c.column_id
        """).fetchall()

        conn.close()

        return rows
'''

test_code = '''
from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_identity_discovery():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_identity_columns")
'''

write_file(ROOT / "store_agent" / "schema_scanner.py", scanner_code)
write_file(ROOT / "tests" / "test_identity_discovery.py", test_code)

print("=" * 80)
print("SYNC-011 INSTALL COMPLETE")
print("=" * 80)
