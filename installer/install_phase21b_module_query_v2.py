# PHASE-21B Module Query Runtime V1

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase21B_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = """
from config.database import get_connection
import uuid

class ModuleRepository:

    def seed_modules(self):
        return 0

    def get_all_modules(self):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            'SELECT module_id,module_code,module_name,description,is_active FROM dbo.modules ORDER BY module_name'
        )

        rows = cur.fetchall()
        conn.close()

        result = []

        for row in rows:
            result.append({
                'module_id': str(row[0]),
                'module_code': row[1],
                'module_name': row[2],
                'description': row[3],
                'is_active': bool(row[4])
            })

        return result

    def get_module_by_id(self, module_id):

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            'SELECT module_id,module_code,module_name,description,is_active FROM dbo.modules WHERE module_id=?',
            module_id
        )

        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'module_id': str(row[0]),
            'module_code': row[1],
            'module_name': row[2],
            'description': row[3],
            'is_active': bool(row[4])
        }
"""
(BACKEND / "repositories" / "module_repository.py").write_text(repo_code, encoding="utf-8")

service_code = """
from repositories.module_repository import ModuleRepository

class ModuleService:

    def seed_modules(self):
        return ModuleRepository().seed_modules()

    def get_all(self):
        return ModuleRepository().get_all_modules()

    def get_by_id(self, module_id):
        return ModuleRepository().get_module_by_id(module_id)
"""
(BACKEND / "services" / "module_service.py").write_text(service_code, encoding="utf-8")

controller_code = """
from fastapi import APIRouter, HTTPException
from services.module_service import ModuleService

router = APIRouter(prefix='/api/modules', tags=['Modules'])

@router.post('/seed')
def seed_modules():
    count = ModuleService().seed_modules()
    return {'status':'success','modules_created':count}

@router.get('')
def get_modules():
    return ModuleService().get_all()

@router.get('/{module_id}')
def get_module(module_id:str):

    module = ModuleService().get_by_id(module_id)

    if not module:
        raise HTTPException(status_code=404, detail='Module not found')

    return module
"""
(BACKEND / "controllers" / "module_controller.py").write_text(controller_code, encoding="utf-8")

print("[SUCCESS] PHASE-21B INSTALLED")
