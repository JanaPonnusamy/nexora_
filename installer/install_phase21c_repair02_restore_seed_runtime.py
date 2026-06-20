#!/usr/bin/env python3
"""
install_phase21c_repair02_restore_seed_runtime.py

PHASE-21C REPAIR-02
Restore seed runtime without impacting existing role permission matrix runtime.
"""

import shutil
from pathlib import Path
from datetime import datetime

INSTALLER_NAME = "install_phase21c_repair02_restore_seed_runtime"
BACKUP_ROOT = "backup_phase21c_repair02"

FILES = [
    "repositories/role_module_access_repository.py",
    "services/role_module_access_service.py",
    "controllers/role_module_access_controller.py",
]

def log(msg):
    print(msg)

def backup_file(root, file_path):
    src = root / file_path
    if not src.exists():
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    dst = backup_dir / file_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

def patch_repository(text):
    if "def seed_super_admin_permissions" in text:
        return text

    block = """

    def seed_super_admin_permissions(self):
        return self.db.execute_sp("sp_RoleModuleAccess_SeedSuperAdmin")
"""
    return text + block

def patch_service(text):
    if "def seed_super_admin_permissions" in text:
        return text

    block = """

    def seed_super_admin_permissions(self):
        return self.repository.seed_super_admin_permissions()
"""
    return text + block

def patch_controller(text):
    if "/seed" in text and "seed_super_admin_permissions" in text:
        return text

    block = """

@router.post("/seed")
def seed_super_admin_permissions(
    service: RoleModuleAccessService = Depends(get_role_module_access_service)
):
    return service.seed_super_admin_permissions()
"""
    return text + block

def main():
    root = Path.cwd()

    log("[INFO] PHASE-21C REPAIR-02")
    log("[INFO] Restoring seed runtime")

    for file_path in FILES:
        full = root / file_path

        if not full.exists():
            log(f"[WARNING] Missing: {file_path}")
            continue

        backup_file(root, file_path)

        text = full.read_text(encoding="utf-8")

        if file_path.endswith("role_module_access_repository.py"):
            text = patch_repository(text)

        elif file_path.endswith("role_module_access_service.py"):
            text = patch_service(text)

        elif file_path.endswith("role_module_access_controller.py"):
            text = patch_controller(text)

        full.write_text(text, encoding="utf-8")
        log(f"[UPDATE] {file_path}")

    log("[SUCCESS]")
    log("POST /api/role-module-access/seed restored")
    log("GET /api/role-module-access/role/{role_id} preserved")

if __name__ == "__main__":
    main()
