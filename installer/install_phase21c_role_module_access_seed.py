# PHASE-21C Role Module Access Seed Runtime V1

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase21C_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class RoleModuleAccessRepository:

    def seed_super_admin_permissions(self):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT role_id FROM dbo.roles WHERE role_name='SUPER_ADMIN'")
        role = cur.fetchone()

        if not role:
            conn.close()
            return 0

        role_id = role[0]

        cur.execute("SELECT module_id FROM dbo.modules WHERE is_active=1")
        modules = cur.fetchall()

        inserted = 0

        for module in modules:

            module_id = module[0]

            cur.execute(
                "SELECT COUNT(*) FROM dbo.role_module_access WHERE role_id=? AND module_id=?",
                role_id,
                module_id
            )

            if cur.fetchone()[0] > 0:
                continue

            cur.execute(
                "INSERT INTO dbo.role_module_access (role_id,module_id,can_view,can_create,can_edit,can_delete,can_export,is_active) VALUES (?,?,?,?,?,?,?,1)",
                role_id,module_id,1,1,1,1,1
            )

            inserted += 1

        conn.commit()
        conn.close()

        return inserted
'''
(BACKEND / 'repositories' / 'role_module_access_repository.py').write_text(repo_code, encoding='utf-8')

service_code = '''
from repositories.role_module_access_repository import RoleModuleAccessRepository

class RoleModuleAccessService:

    def seed_super_admin_permissions(self):
        return RoleModuleAccessRepository().seed_super_admin_permissions()
'''
(BACKEND / 'services' / 'role_module_access_service.py').write_text(service_code, encoding='utf-8')

controller_code = '''
from fastapi import APIRouter
from services.role_module_access_service import RoleModuleAccessService

router = APIRouter(prefix='/api/role-module-access', tags=['Role Module Access'])

@router.post('/seed')
def seed_permissions():

    count = RoleModuleAccessService().seed_super_admin_permissions()

    return {
        'status':'success',
        'records_created':count
    }
'''
(BACKEND / 'controllers' / 'role_module_access_controller.py').write_text(controller_code, encoding='utf-8')

print('[SUCCESS] PHASE-21C INSTALLED')
