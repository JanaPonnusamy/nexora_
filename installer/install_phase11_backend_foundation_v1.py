
"""
NEXORA
PHASE-11
Backend Foundation V1 Installer

Creates:
- Backend Solution Structure
- API Layer
- Service Layer
- Repository Layer
- DTO Layer
- Middleware Layer
- Configuration Layer
- Test Structure
- Logging Structure
"""

from pathlib import Path
from datetime import datetime
import shutil
import logging
import sys

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"
LOGS = ROOT / "logs"

FOLDERS = [
    BACKEND,
    BACKEND / "api",
    BACKEND / "controllers",
    BACKEND / "services",
    BACKEND / "repositories",
    BACKEND / "models",
    BACKEND / "dtos",
    BACKEND / "middleware",
    BACKEND / "config",
    BACKEND / "sql",
    BACKEND / "tests",
    BACKEND / "docs",
    LOGS
]

FILES = [
    BACKEND / "__init__.py",
    BACKEND / "api" / "__init__.py",
    BACKEND / "controllers" / "__init__.py",
    BACKEND / "services" / "__init__.py",
    BACKEND / "repositories" / "__init__.py",
    BACKEND / "models" / "__init__.py",
    BACKEND / "dtos" / "__init__.py",
    BACKEND / "middleware" / "__init__.py",
    BACKEND / "config" / "__init__.py",
    BACKEND / "tests" / "__init__.py"
]

def backup():
    if BACKEND.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = ROOT / "backup" / f"backend_{ts}"
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BACKEND, backup_dir)
        print(f"[INFO] Backup Created : {backup_dir}")

def setup_logs():
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOGS / "install.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

def create_folders():
    for folder in FOLDERS:
        if folder.exists():
            print(f"[SKIP] {folder}")
        else:
            folder.mkdir(parents=True, exist_ok=True)
            print(f"[CREATE] {folder}")

def create_files():
    for file in FILES:
        if file.exists():
            print(f"[SKIP] {file}")
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("", encoding="utf-8")
            print(f"[CREATE] {file}")

def main():
    print("[INFO] NEXORA PHASE-11 INSTALLER STARTED")
    setup_logs()
    backup()
    create_folders()
    create_files()
    print("[SUCCESS] Backend Foundation V1 Installed")

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"[ERROR] {ex}")
        sys.exit(1)
