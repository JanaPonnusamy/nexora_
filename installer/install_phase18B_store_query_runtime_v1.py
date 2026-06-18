
"""
NEXORA PHASE-18B Store Query Runtime V1
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase18B_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class StoreRepository:

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active
        FROM dbo.stores
        ORDER BY store_code
        """)
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_by_id(self, store_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active
        FROM dbo.stores
        WHERE store_id = ?
        """, store_id)
        row = cur.fetchone()
        conn.close()
        return row

    def get_by_tenant(self, tenant_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT store_id,tenant_id,store_code,store_name,server_name,database_name,is_active
        FROM dbo.stores
        WHERE tenant_id = ?
        ORDER BY store_code
        """, tenant_id)
        rows = cur.fetchall()
        conn.close()
        return rows
'''
(BACKEND/"repositories"/"store_repository.py").write_text(repo_code, encoding="utf-8")

service_code = '''
from repositories.store_repository import StoreRepository

class StoreService:
    def get_all(self):
        return StoreRepository().get_all()

    def get_by_id(self, store_id):
        return StoreRepository().get_by_id(store_id)

    def get_by_tenant(self, tenant_id):
        return StoreRepository().get_by_tenant(tenant_id)
'''
(BACKEND/"services"/"store_service.py").write_text(service_code, encoding="utf-8")

controller_code = '''
from fastapi import APIRouter
from services.store_service import StoreService

router = APIRouter(prefix="/api/stores", tags=["Stores"])

@router.get("")
def get_stores():
    rows = StoreService().get_all()
    return [{"store_id":str(r[0]),"tenant_id":str(r[1]),"store_code":r[2],"store_name":r[3],"server_name":r[4],"database_name":r[5],"is_active":bool(r[6])} for r in rows]

@router.get("/tenant/{tenant_id}")
def get_by_tenant(tenant_id:str):
    rows = StoreService().get_by_tenant(tenant_id)
    return [{"store_id":str(r[0]),"store_code":r[2],"store_name":r[3]} for r in rows]

@router.get("/{store_id}")
def get_store(store_id:str):
    r = StoreService().get_by_id(store_id)
    if not r:
        return {"error":"Store Not Found"}
    return {"store_id":str(r[0]),"tenant_id":str(r[1]),"store_code":r[2],"store_name":r[3],"server_name":r[4],"database_name":r[5],"is_active":bool(r[6])}
'''
(BACKEND/"controllers"/"store_controller.py").write_text(controller_code, encoding="utf-8")

print("[SUCCESS] PHASE-18B INSTALLED")
