#!/usr/bin/env python3
import shutil
from pathlib import Path
from datetime import datetime

BACKEND = Path(r"E:\Nexora\backend")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = BACKEND / "_backup_phase21c_repair02" / STAMP

FILES = {
    BACKEND / "repositories" / "role_module_access_repository.py": """from config.database import get_connection

class RoleModuleAccessRepository:

    def seed_super_admin_permissions(self):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("EXEC dbo.sp_RoleModuleAccess_Seed")

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Super Admin permissions seeded successfully"
        }

    def get_role_permission_matrix(self, role_id):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT r.role_id,r.role_name,m.module_id,m.module_code,m.module_name,rma.can_view,rma.can_create,rma.can_edit,rma.can_delete,rma.can_export FROM dbo.role_module_access rma INNER JOIN dbo.roles r ON rma.role_id=r.role_id INNER JOIN dbo.modules m ON rma.module_id=m.module_id WHERE rma.role_id=? ORDER BY m.module_name",
            role_id
        )

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        modules = []

        for row in rows:
            modules.append({
                "module_id": str(row[2]),
                "module_code": row[3],
                "module_name": row[4],
                "can_view": bool(row[5]),
                "can_create": bool(row[6]),
                "can_edit": bool(row[7]),
                "can_delete": bool(row[8]),
                "can_export": bool(row[9])
            })

        return {
            "role_id": str(rows[0][0]),
            "role_name": rows[0][1],
            "total_modules": len(modules),
            "modules": modules
        }
""",
    BACKEND / "services" / "role_module_access_service.py": """from repositories.role_module_access_repository import RoleModuleAccessRepository

class RoleModuleAccessService:

    def seed_super_admin_permissions(self):
        return RoleModuleAccessRepository().seed_super_admin_permissions()

    def get_role_permission_matrix(self, role_id):
        return RoleModuleAccessRepository().get_role_permission_matrix(role_id)
""",
    BACKEND / "controllers" / "role_module_access_controller.py": """from fastapi import APIRouter
from services.role_module_access_service import RoleModuleAccessService

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.post("/seed")
def seed_permissions():
    return RoleModuleAccessService().seed_super_admin_permissions()

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str):
    return RoleModuleAccessService().get_role_permission_matrix(role_id)
"""
}

print("[INFO] PHASE-21C REPAIR-02 START")

for target, code in FILES.items():
    if not target.exists():
        print(f"[ERROR] Missing: {target}")
        continue

    backup_target = BACKUP / target.relative_to(BACKEND)
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup_target)

    target.write_text(code, encoding="utf-8")
    print(f"[UPDATE] {target}")

print("[SUCCESS] PHASE-21C REPAIR-02 COMPLETE")
