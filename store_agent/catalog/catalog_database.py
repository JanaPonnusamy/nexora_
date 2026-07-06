
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
