from pathlib import Path

ROOT = Path(r'E:\Nexora')

runtime_dir = ROOT / 'store_agent' / 'runtime'
runtime_dir.mkdir(parents=True, exist_ok=True)

(runtime_dir / 'metadata_runtime_reader.py').write_text('''
import sqlite3
from store_agent.catalog.catalog_models import CATALOG_DB_PATH

class MetadataRuntimeReader:

    def get_tables(self):

        conn = sqlite3.connect(CATALOG_DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            rows = conn.execute(
                "SELECT * FROM sync_table_catalog WHERE is_active=1 ORDER BY sync_order"
            ).fetchall()

            return [dict(x) for x in rows]

        finally:
            conn.close()

    def get_columns(self, table_name):

        conn = sqlite3.connect(CATALOG_DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            rows = conn.execute(
                "SELECT * FROM sync_column_catalog WHERE table_name=? ORDER BY column_order",
                (table_name,)
            ).fetchall()

            return [dict(x) for x in rows]

        finally:
            conn.close()
''', encoding='utf-8')

(ROOT / 'tests' / 'test_metadata_runtime_reader.py').write_text('''
from store_agent.runtime.metadata_runtime_reader import MetadataRuntimeReader

def test_metadata_reader():
    reader = MetadataRuntimeReader()
    tables = reader.get_tables()
    assert len(tables) > 0
''', encoding='utf-8')

print('SYNC-027D INSTALL COMPLETE')
