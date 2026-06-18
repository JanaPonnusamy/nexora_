# PHASE-21A REPAIR-01 Module Seed Runtime V1

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase21A_repair01_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection
import uuid

class ModuleRepository:

    def seed_modules(self):

        modules = [
            ("DASHBOARD","Dashboard","Application Dashboard"),
            ("TENANTS","Tenants","Tenant Management"),
            ("STORES","Stores","Store Management"),
            ("USERS","Users","User Management"),
            ("ROLES","Roles","Role Management"),
            ("MODULES","Modules","Module Management"),
            ("PERMISSIONS","Permissions","Permission Management"),
            ("SYNC","Sync","Synchronization"),
            ("SYNC_JOBS","Sync Jobs","Synchronization Jobs"),
            ("SYNC_MONITOR","Sync Monitor","Synchronization Monitoring"),
            ("REPORTS","Reports","Reporting"),
            ("SETTINGS","Settings","Application Settings"),
            ("AUDIT_LOG","Audit Log","Audit Logging")
        ]

        conn = get_connection()
        cur = conn.cursor()

        inserted = 0

        for module_code, module_name, description in modules:

            cur.execute(
                "SELECT COUNT(*) FROM dbo.modules WHERE module_code=?",
                module_code
            )

            if cur.fetchone()[0] > 0:
                continue

            cur.execute(
                "INSERT INTO dbo.modules (module_id,module_code,module_name,description,is_active) VALUES (?,?,?,?,1)",
                str(uuid.uuid4()),
                module_code,
                module_name,
                description
            )

            inserted += 1

        conn.commit()
        conn.close()

        return inserted
'''
(BACKEND / "repositories" / "module_repository.py").write_text(repo_code, encoding="utf-8")

service_code = '''
from repositories.module_repository import ModuleRepository

class ModuleService:

    def seed_modules(self):
        return ModuleRepository().seed_modules()
'''
(BACKEND / "services" / "module_service.py").write_text(service_code, encoding="utf-8")

controller_code = '''
from fastapi import APIRouter
from services.module_service import ModuleService

router = APIRouter(prefix="/api/modules", tags=["Modules"])

@router.post("/seed")
def seed_modules():
    count = ModuleService().seed_modules()

    return {
        "status":"success",
        "modules_created":count
    }
'''
(BACKEND / "controllers" / "module_controller.py").write_text(controller_code, encoding="utf-8")

app_file = BACKEND / "api" / "app.py"
txt = app_file.read_text(encoding="utf-8")

if "module_router" not in txt:

    txt = txt.replace(
        "from controllers.user_role_controller import router as user_role_router",
        "from controllers.user_role_controller import router as user_role_router\\nfrom controllers.module_controller import router as module_router"
    )

    txt = txt.replace(
        "app.include_router(user_role_router)",
        "app.include_router(user_role_router)\\napp.include_router(module_router)"
    )

app_file.write_text(txt, encoding="utf-8")

print("[SUCCESS] PHASE-21A REPAIR-01 INSTALLED")
