"""
NEXORA PHASE-11 INSTALLER
Backend Foundation V1
Creates folder structure only.
"""

from pathlib import Path
import logging
import shutil
from datetime import datetime

ROOT = Path(r"E:\Nexora")
PROJECT = ROOT / "backend"
LOGS = ROOT / "logs"

FOLDERS = [
    PROJECT / "api",
    PROJECT / "controllers",
    PROJECT / "services",
    PROJECT / "repositories",
    PROJECT / "models",
    PROJECT / "dtos",
    PROJECT / "middleware",
    PROJECT / "config",
    PROJECT / "sql",
    PROJECT / "tests",
    LOGS
]

def setup_logs():
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOGS / "install.log"),
        level=logging.INFO,
        format="%(asctime)s %(message)s"
    )

def backup():
    if PROJECT.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = ROOT / f"backup_{ts}"
        shutil.copytree(PROJECT, target)

def create():
    for folder in FOLDERS:
        folder.mkdir(parents=True, exist_ok=True)
        print(f"[CREATE] {folder}")

if __name__ == "__main__":
    setup_logs()
    backup()
    create()
    print("[SUCCESS] Backend Foundation V1 Structure Created")
