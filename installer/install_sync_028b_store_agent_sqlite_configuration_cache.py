from pathlib import Path

ROOT = Path(r'E:\Nexora')

CACHE_DIR = ROOT / 'store_agent' / 'config_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

(CACHE_DIR / 'configuration_cache_database.py').write_text('''import sqlite3

DB_PATH = r"E:\\Nexora\\data\\catalog.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def initialize_database():
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS agent_configuration (store_id TEXT PRIMARY KEY, tenant_id TEXT, store_code TEXT, store_name TEXT, server_name TEXT, database_name TEXT, username TEXT, password_encrypted TEXT, connection_type TEXT, is_active INTEGER, downloaded_at TEXT)")
        conn.commit()
    finally:
        conn.close()
''', encoding='utf-8')

(CACHE_DIR / 'configuration_cache_repository.py').write_text('''from .configuration_cache_database import get_connection, initialize_database

def initialize():
    initialize_database()

def upsert_configuration(config):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO agent_configuration VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                config.get('store_id'),
                config.get('tenant_id'),
                config.get('store_code'),
                config.get('store_name'),
                config.get('server_name'),
                config.get('database_name'),
                config.get('username'),
                config.get('password_encrypted'),
                config.get('connection_type'),
                config.get('is_active'),
                config.get('downloaded_at')
            )
        )
        conn.commit()
    finally:
        conn.close()

def get_configuration(store_id):
    conn = get_connection()
    conn.row_factory = __import__('sqlite3').Row
    try:
        row = conn.execute('SELECT * FROM agent_configuration WHERE store_id=?',(store_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
''', encoding='utf-8')

(CACHE_DIR / 'configuration_cache_service.py').write_text('''from .configuration_cache_repository import upsert_configuration, get_configuration

class ConfigurationCacheService:

    def save_configuration(self, config):
        upsert_configuration(config)

    def load_configuration(self, store_id):
        return get_configuration(store_id)
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_configuration_cache.py').write_text('''def test_import():
    from store_agent.config_cache.configuration_cache_service import ConfigurationCacheService
    assert ConfigurationCacheService is not None
''', encoding='utf-8')

print('SYNC-028B INSTALL COMPLETE')
