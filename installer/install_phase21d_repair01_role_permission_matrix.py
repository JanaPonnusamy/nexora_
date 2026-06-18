# PHASE-21D REPAIR-01
# Role Module Access Query Response Model

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase21D_repair01_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class RoleModuleAccessRepository:

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
'''
(BACKEND / "repositories" / "role_module_access_repository.py").write_text(repo_code, encoding="utf-8")

service_code = '''
from repositories.role_module_access_repository import RoleModuleAccessRepository

class RoleModuleAccessService:

    def get_role_permission_matrix(self, role_id):
        return RoleModuleAccessRepository().get_role_permission_matrix(role_id)
'''
(BACKEND / "services" / "role_module_access_service.py").write_text(service_code, encoding="utf-8")

controller_code = '''
from fastapi import APIRouter
from services.role_module_access_service import RoleModuleAccessService

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str):
    return RoleModuleAccessService().get_role_permission_matrix(role_id)
'''
(BACKEND / "controllers" / "role_module_access_controller.py").write_text(controller_code, encoding="utf-8")

print("[SUCCESS] PHASE-21D REPAIR-01 INSTALLED")
