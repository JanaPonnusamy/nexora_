from pathlib import Path
import sqlite3

ROOT = Path(r'E:\Nexora')

catalog_dir = ROOT / 'store_agent' / 'catalog'
data_dir = ROOT / 'data'

catalog_dir.mkdir(parents=True, exist_ok=True)
data_dir.mkdir(parents=True, exist_ok=True)

(catalog_dir / 'catalog_models.py').write_text(
    'CATALOG_DB_PATH = r"E:\\\\Nexora\\\\data\\\\catalog.db"\n',
    encoding='utf-8'
)

(catalog_dir / 'catalog_database.py').write_text('''
import sqlite3
from .catalog_models import CATALOG_DB_PATH

def get_connection():
    return sqlite3.connect(CATALOG_DB_PATH)

def initialize_database():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_table_catalog
        (
            sync_table_id TEXT PRIMARY KEY,
            table_name TEXT NOT NULL,
            is_active INTEGER NOT NULL,
            sync_mode TEXT,
            watermark_column TEXT,
            window_days INTEGER,
            window_months INTEGER,
            custom_where TEXT,
            sync_order INTEGER,
            created_at TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_column_catalog
        (
            mapping_id TEXT PRIMARY KEY,
            sync_table_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            data_type TEXT,
            is_selected INTEGER,
            is_pk INTEGER,
            is_hash INTEGER,
            is_watermark INTEGER,
            column_order INTEGER,
            created_at TEXT
        )
        """)
        conn.commit()
    finally:
        conn.close()
''', encoding='utf-8')

(catalog_dir / 'catalog_repository.py').write_text('''
from .catalog_database import get_connection, initialize_database

initialize_database()

def get_table_count():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sync_table_catalog")
        return cursor.fetchone()[0]
    finally:
        conn.close()
''', encoding='utf-8')

db_path = data_dir / 'catalog.db'

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS sync_table_catalog (
sync_table_id TEXT PRIMARY KEY,
table_name TEXT NOT NULL,
is_active INTEGER NOT NULL,
sync_mode TEXT,
watermark_column TEXT,
window_days INTEGER,
window_months INTEGER,
custom_where TEXT,
sync_order INTEGER,
created_at TEXT
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS sync_column_catalog (
mapping_id TEXT PRIMARY KEY,
sync_table_id TEXT NOT NULL,
table_name TEXT NOT NULL,
column_name TEXT NOT NULL,
data_type TEXT,
is_selected INTEGER,
is_pk INTEGER,
is_hash INTEGER,
is_watermark INTEGER,
column_order INTEGER,
created_at TEXT
)''')

conn.commit()
conn.close()

print('SYNC-027C-A INSTALL COMPLETE')
