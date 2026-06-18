# PHASE-21D Role Module Access Query Runtime V1

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase21D_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class RoleModuleAccessRepository:

    def get_by_role(self, role_id):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                m.module_id,
                m.module_code,
                m.module_name,
                rma.can_view,
                rma.can_create,
                rma.can_edit,
                rma.can_delete,
                rma.can_export
            FROM dbo.role_module_access rma
            INNER JOIN dbo.modules m
                ON rma.module_id = m.module_id
            WHERE rma.role_id = ?
            ORDER BY m.module_name
            """,
            role_id
        )

        rows = cur.fetchall()
        conn.close()

        result = []

        for row in rows:
            result.append({
                "module_id": str(row[0]),
                "module_code": row[1],
                "module_name": row[2],
                "can_view": bool(row[3]),
                "can_create": bool(row[4]),
                "can_edit": bool(row[5]),
                "can_delete": bool(row[6]),
                "can_export": bool(row[7])
            })

        return result
'''
(BACKEND / "repositories" / "role_module_access_repository.py").write_text(repo_code, encoding="utf-8")

service_code = '''
from repositories.role_module_access_repository import RoleModuleAccessRepository

class RoleModuleAccessService:

    def get_by_role(self, role_id):
        return RoleModuleAccessRepository().get_by_role(role_id)
'''
(BACKEND / "services" / "role_module_access_service.py").write_text(service_code, encoding="utf-8")

controller_code = '''
from fastapi import APIRouter
from services.role_module_access_service import RoleModuleAccessService

router = APIRouter(prefix="/api/role-module-access", tags=["Role Module Access"])

@router.get("/role/{role_id}")
def get_role_permissions(role_id:str):
    return RoleModuleAccessService().get_by_role(role_id)
'''
(BACKEND / "controllers" / "role_module_access_controller.py").write_text(controller_code, encoding="utf-8")

print("[SUCCESS] PHASE-21D INSTALLED")
