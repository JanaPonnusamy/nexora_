
"""
NEXORA
PHASE-12
Backend Core Infrastructure V1 Installer
"""

from pathlib import Path
from datetime import datetime
import shutil
import sys

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"
LOGS = ROOT / "logs"

FILES = {
    BACKEND / "api" / "app.py": "# FastAPI Application Entry Point\n",
    BACKEND / "config" / "settings.py": "# Application Settings\n",
    BACKEND / "config" / "database.py": "# SQL Server Connection Manager\n",
    BACKEND / "config" / "logger.py": "# Logging Configuration\n",
    BACKEND / "middleware" / "exception_middleware.py": "# Exception Middleware\n",
    BACKEND / "middleware" / "request_middleware.py": "# Request Middleware\n",
    BACKEND / "requirements.txt":
"""fastapi
uvicorn
sqlalchemy
pyodbc
pydantic
python-dotenv
""",
    BACKEND / ".env.example":
"""DB_SERVER=localhost
DB_DATABASE=NEXORA_PLATFORM
DB_USERNAME=sa
DB_PASSWORD=password
"""
}

def backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = ROOT / "backup" / f"phase12_{ts}"
    if BACKEND.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BACKEND, target)
        print(f"[INFO] Backup Created : {target}")

def create_or_update():
    for file_path, content in FILES.items():
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists():
            file_path.write_text(content, encoding="utf-8")
            print(f"[UPDATE] {file_path}")
        else:
            file_path.write_text(content, encoding="utf-8")
            print(f"[CREATE] {file_path}")

def create_logs():
    LOGS.mkdir(parents=True, exist_ok=True)

def main():
    print("[INFO] PHASE-12 INSTALL STARTED")
    backup()
    create_logs()
    create_or_update()
    print("[SUCCESS] PHASE-12 INSTALLED")

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"[ERROR] {ex}")
        sys.exit(1)
