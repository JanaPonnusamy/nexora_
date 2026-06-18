"""
PHASE-21B Module Query Runtime V1 Installer
NEXORA Platform
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
BACKUP_DIR = ROOT / "backup" / f"phase21b_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LOG_DIR = ROOT / "logs"

def log(msg):
    print(msg)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "install.log", "a", encoding="utf-8") as f:
        f.write(msg + "\\n")

def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    log(f"[INFO] Backup folder: {BACKUP_DIR}")

def write_file(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    action = "UPDATE" if path.exists() else "CREATE"
    path.write_text(content, encoding="utf-8")
    log(f"[{action}] {path}")

def main():
    backup()

    write_file(
        "app/repositories/module_repository.py",
        "# Phase-21B Module Repository\\n"
        "class ModuleRepository:\\n"
        "    pass\\n"
    )

    write_file(
        "app/services/module_service.py",
        "# Phase-21B Module Service\\n"
        "class ModuleService:\\n"
        "    pass\\n"
    )

    write_file(
        "app/controllers/module_controller.py",
        "# Phase-21B Module Controller\\n"
        "router = None\\n"
    )

    write_file(
        "tests/test_phase21b_modules.txt",
        "GET /api/modules\\nGET /api/modules/{module_id}\\n"
    )

    log("[SUCCESS] Phase-21B installer completed")

if __name__ == '__main__':
    main()
