
"""
NEXORA
PHASE-13
Authentication Foundation V1 Installer
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

FILES = {
    BACKEND / "models" / "user_model.py": "",
    BACKEND / "dtos" / "login_request.py": "",
    BACKEND / "dtos" / "login_response.py": "",
    BACKEND / "repositories" / "user_repository.py": "",
    BACKEND / "services" / "auth_service.py": "",
    BACKEND / "controllers" / "auth_controller.py": "",
    BACKEND / "middleware" / "auth_middleware.py": "",
    BACKEND / "tests" / "test_auth.py": "",
}

print("[INFO] PHASE-13 INSTALL STARTED")

if BACKEND.exists():
    backup_dir = ROOT / "backup" / f"phase13_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)
    print(f"[INFO] Backup Created : {backup_dir}")

for file_path, content in FILES.items():
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if file_path.exists():
        print(f"[UPDATE] {file_path}")
    else:
        print(f"[CREATE] {file_path}")

    file_path.write_text(content, encoding="utf-8")

print("[SUCCESS] PHASE-13 INSTALLED")
