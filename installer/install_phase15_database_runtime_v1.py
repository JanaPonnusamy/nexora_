
"""
NEXORA
PHASE-15
Database Runtime V1 Installer
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

ENV_CONTENT = """DB_SERVER=CLIENT-3\SQLEXPRESS
DB_DATABASE=NEXORA_PLATFORM
DB_AUTH_MODE=WINDOWS
DB_USERNAME=sa
DB_PASSWORD=
"""

DB_CONTENT = """import os
import pyodbc

def get_connection():
    conn_str = (
        'DRIVER={SQL Server};'
        f'SERVER={os.getenv("DB_SERVER","CLIENT-3\\\\SQLEXPRESS")};'
        f'DATABASE={os.getenv("DB_DATABASE","NEXORA_PLATFORM")};'
        'Trusted_Connection=yes;'
    )
    return pyodbc.connect(conn_str)
"""

APP_APPEND = """

from config.database import get_connection

@app.get('/health/db')
def health_db():
    try:
        conn = get_connection()
        conn.close()
        return {'status':'healthy','database':'connected'}
    except Exception as ex:
        return {'status':'failed','error':str(ex)}
"""

FILES = {
    BACKEND / ".env": ENV_CONTENT,
    BACKEND / "config" / "database.py": DB_CONTENT,
}

print("[INFO] PHASE-15 INSTALL STARTED")

backup_dir = ROOT / "backup" / f"phase15_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

for fp, content in FILES.items():
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    print(f"[UPDATE] {fp}")

app_file = BACKEND / "api" / "app.py"
if app_file.exists():
    txt = app_file.read_text(encoding="utf-8")
    if "/health/db" not in txt:
        app_file.write_text(txt + APP_APPEND, encoding="utf-8")
    print(f"[UPDATE] {app_file}")

print("[SUCCESS] PHASE-15 INSTALLED")
