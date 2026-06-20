# SYNC-007 SQL Server Connection Layer Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync007_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

config_code = """
SQL_SERVER = ""
SQL_DATABASE = ""
SQL_USERNAME = ""
SQL_PASSWORD = ""

STORE_ID = ""
HO_API_URL = "http://127.0.0.1:8000"
"""

database_code = """
import pyodbc
from store_agent.config import (
    SQL_SERVER,
    SQL_DATABASE,
    SQL_USERNAME,
    SQL_PASSWORD
)

def get_connection():
    conn_str = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        f'SERVER={SQL_SERVER};'
        f'DATABASE={SQL_DATABASE};'
        f'UID={SQL_USERNAME};'
        f'PWD={SQL_PASSWORD};'
        'TrustServerCertificate=yes;'
    )
    return pyodbc.connect(conn_str)
"""

test_code = """
from store_agent.database import get_connection

def test_database_module_exists():
    assert callable(get_connection)
"""

write_file(ROOT / "store_agent" / "config.py", config_code)
write_file(ROOT / "store_agent" / "database.py", database_code)
write_file(ROOT / "tests" / "test_database_connection.py", test_code)

print("=" * 80)
print("SYNC-007 INSTALL COMPLETE")
print("=" * 80)
