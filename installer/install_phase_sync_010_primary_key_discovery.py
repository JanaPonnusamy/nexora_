# SYNC-010 Primary Key Discovery Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync010_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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

    def get_primary_keys(self):

        conn = get_connection()
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            c.name AS column_name
        FROM sys.indexes i
        INNER JOIN sys.index_columns ic
            ON i.object_id = ic.object_id
            AND i.index_id = ic.index_id
        INNER JOIN sys.columns c
            ON ic.object_id = c.object_id
            AND ic.column_id = c.column_id
        INNER JOIN sys.tables t
            ON t.object_id = i.object_id
        INNER JOIN sys.schemas s
            ON s.schema_id = t.schema_id
        WHERE i.is_primary_key = 1
        ORDER BY s.name,t.name,c.column_id
        """).fetchall()

        conn.close()

        return rows
'''

test_code = '''
from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_primary_key_discovery():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_primary_keys")
'''

write_file(ROOT / "store_agent" / "schema_scanner.py", scanner_code)
write_file(ROOT / "tests" / "test_primary_key_discovery.py", test_code)

print("=" * 80)
print("SYNC-010 INSTALL COMPLETE")
print("=" * 80)
