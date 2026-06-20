# SYNC-009 INFORMATION_SCHEMA Column Discovery Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync009_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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

    def get_columns(self):

        conn = get_connection()
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            TABLE_SCHEMA,
            TABLE_NAME,
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            IS_NULLABLE,
            ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        ORDER BY TABLE_SCHEMA,TABLE_NAME,ORDINAL_POSITION
        """).fetchall()

        conn.close()

        return rows
'''

test_code = '''
from store_agent.schema_scanner import SchemaScanner

def test_schema_scanner_has_get_columns():
    scanner = SchemaScanner()
    assert hasattr(scanner, "get_columns")
'''

write_file(ROOT / "store_agent" / "schema_scanner.py", scanner_code)
write_file(ROOT / "tests" / "test_column_discovery.py", test_code)

print("=" * 80)
print("SYNC-009 INSTALL COMPLETE")
print("=" * 80)
