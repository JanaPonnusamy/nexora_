
"""
NEXORA
PHASE-17A
Tenant Create Runtime V1
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase17A_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection
import uuid

class TenantRepository:

    def create_default_tenant(self):
        conn = get_connection()
        cur = conn.cursor()

        tenant_id = str(uuid.uuid4())

        sql = """
        INSERT INTO dbo.tenants
        (
            tenant_id,
            tenant_code,
            tenant_abbreviation,
            tenant_name,
            db_name,
            is_active,
            created_at
        )
        VALUES
        (
            ?,
            'NATHAN',
            'Nathan',
            'Nathan Medicals - Perundurai',
            'NEXORA_PLATFORM',
            1,
            GETDATE()
        )
        """

        cur.execute(sql, tenant_id)
        conn.commit()
        conn.close()

        return tenant_id
'''

service_code = '''
from repositories.tenant_repository import TenantRepository

class TenantService:

    def create_default_tenant(self):
        return TenantRepository().create_default_tenant()
'''

controller_code = '''
from fastapi import APIRouter
from services.tenant_service import TenantService

router = APIRouter(prefix="/api/tenants", tags=["Tenants"])

@router.post("/seed")
def seed_tenant():
    tenant_id = TenantService().create_default_tenant()

    return {
        "status":"success",
        "tenant_id":tenant_id
    }
'''

(BACKEND / "repositories" / "tenant_repository.py").write_text(repo_code, encoding="utf-8")
(BACKEND / "services" / "tenant_service.py").write_text(service_code, encoding="utf-8")
(BACKEND / "controllers" / "tenant_controller.py").write_text(controller_code, encoding="utf-8")

print("[SUCCESS] PHASE-17A INSTALLED")
