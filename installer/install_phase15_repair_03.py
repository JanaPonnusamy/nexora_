
"""
NEXORA
PHASE-15 REPAIR-03
SQL Authentication Fix
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase15_repair03_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

env_content = """DB_SERVER=192.168.10.73
DB_DATABASE=NEXORA_PLATFORM
DB_AUTH_MODE=SQL
DB_USERNAME=sa
DB_PASSWORD=Admin123
DB_DRIVER=ODBC Driver 17 for SQL Server
"""

db_content = """import pyodbc

def get_connection():
    conn_str = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=192.168.10.73;'
        'DATABASE=NEXORA_PLATFORM;'
        'UID=sa;'
        'PWD=Admin123;'
        'TrustServerCertificate=yes;'
    )
    return pyodbc.connect(conn_str)
"""

(BACKEND / ".env").write_text(env_content, encoding="utf-8")
(BACKEND / "config" / "database.py").write_text(db_content, encoding="utf-8")

print("[UPDATE] .env")
print("[UPDATE] config/database.py")
print("[SUCCESS] PHASE-15 REPAIR-03 APPLIED")
