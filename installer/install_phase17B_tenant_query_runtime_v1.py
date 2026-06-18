
"""
NEXORA PHASE-17B Tenant Query Runtime V1
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase17B_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class TenantRepository:

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active
        FROM dbo.tenants
        ORDER BY tenant_name
        """)
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_by_id(self, tenant_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT tenant_id,tenant_code,tenant_abbreviation,tenant_name,db_name,is_active
        FROM dbo.tenants
        WHERE tenant_id = ?
        """, tenant_id)
        row = cur.fetchone()
        conn.close()
        return row
'''
(BACKEND / "repositories" / "tenant_repository.py").write_text(repo_code, encoding="utf-8")

service_code = '''
from repositories.tenant_repository import TenantRepository

class TenantService:
    def get_all(self):
        return TenantRepository().get_all()

    def get_by_id(self, tenant_id):
        return TenantRepository().get_by_id(tenant_id)
'''
(BACKEND / "services" / "tenant_service.py").write_text(service_code, encoding="utf-8")

controller_code = '''
from fastapi import APIRouter
from services.tenant_service import TenantService

router = APIRouter(prefix="/api/tenants", tags=["Tenants"])

@router.get("")
def get_tenants():
    rows = TenantService().get_all()
    return [{"tenant_id":str(r[0]),"tenant_code":r[1],"tenant_abbreviation":r[2],"tenant_name":r[3],"db_name":r[4],"is_active":bool(r[5])} for r in rows]

@router.get("/{tenant_id}")
def get_tenant(tenant_id:str):
    r = TenantService().get_by_id(tenant_id)
    if not r:
        return {"error":"Tenant Not Found"}
    return {"tenant_id":str(r[0]),"tenant_code":r[1],"tenant_abbreviation":r[2],"tenant_name":r[3],"db_name":r[4],"is_active":bool(r[5])}
'''
(BACKEND / "controllers" / "tenant_controller.py").write_text(controller_code, encoding="utf-8")

print("[SUCCESS] PHASE-17B INSTALLED")
