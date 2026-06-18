
"""
NEXORA
PHASE-18A
Store Seed Runtime V1
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase18A_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = """
from config.database import get_connection
import uuid

class StoreRepository:

    def seed_stores(self):

        tenant_id = 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D'

        stores = [
            ('NMW','Nathan Medicals Main Branch','DESKTOP-745PMO0\\\\SQLEXPRESS','Nathanw','','LAN','NMW'),
            ('NMS','WantedNMS','SERVER-S\\\\SQLEXPRESS','Rshopaid','1000135,1001286,1001379,1000668,1001374,1001263','LAN','NMS'),
            ('NMC','WantedNMC','DESKTOP-LOCNRSU\\\\SQLEXPRESS','Rshopaid','1002700,1002701,1002702,1002699,1000996,1001118','LAN','NMC'),
            ('NMG','WantedNMG','KSERVER-PC\\\\SQLEXPRESS','Shopaid','721,720,437,745','LAN','NMG'),
            ('NMA','Nathan Medicals A Branch','MSERVER-PC\\\\SQLEXPRESS','RShopaidLive','1000621,1000460,1000973,1000608,1001186,1001187,1001188','LAN','NMA')
        ]

        conn = get_connection()
        cur = conn.cursor()

        inserted = 0

        for s in stores:
            cur.execute(\"\"\"
            INSERT INTO dbo.stores
            (
                store_id,
                tenant_id,
                store_code,
                store_name,
                server_name,
                database_name,
                username,
                connection_type,
                branch_codes,
                is_active,
                store_abbreviation,
                created_at
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?,?,1,?,GETDATE()
            )
            \"\"\",
            str(uuid.uuid4()),
            tenant_id,
            s[0],
            s[1],
            s[2],
            s[3],
            'sa',
            s[5],
            s[4],
            s[6])

            inserted += 1

        conn.commit()
        conn.close()

        return inserted
"""

service_code = """
from repositories.store_repository import StoreRepository

class StoreService:

    def seed_stores(self):
        return StoreRepository().seed_stores()
"""

controller_code = """
from fastapi import APIRouter
from services.store_service import StoreService

router = APIRouter(prefix='/api/stores', tags=['Stores'])

@router.post('/seed')
def seed_stores():
    count = StoreService().seed_stores()

    return {
        'status':'success',
        'stores_created':count
    }
"""

(BACKEND / "repositories" / "store_repository.py").write_text(repo_code, encoding="utf-8")
(BACKEND / "services" / "store_service.py").write_text(service_code, encoding="utf-8")
(BACKEND / "controllers" / "store_controller.py").write_text(controller_code, encoding="utf-8")

app_file = BACKEND / "api" / "app.py"
txt = app_file.read_text(encoding="utf-8")

if "store_controller" not in txt:
    txt = txt.replace(
        "from controllers.tenant_controller import router as tenant_router",
        "from controllers.tenant_controller import router as tenant_router\nfrom controllers.store_controller import router as store_router"
    )

    txt = txt.replace(
        "app.include_router(tenant_router)",
        "app.include_router(tenant_router)\napp.include_router(store_router)"
    )

app_file.write_text(txt, encoding="utf-8")

print("[SUCCESS] PHASE-18A INSTALLED")
