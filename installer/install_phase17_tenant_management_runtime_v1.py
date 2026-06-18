
"""
NEXORA
PHASE-17
Tenant Management Runtime V1 Installer
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase17_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

files = {
    BACKEND / "dtos" / "tenant_request.py": """
from pydantic import BaseModel

class TenantRequest(BaseModel):
    tenant_name: str
    tenant_code: str
""",
    BACKEND / "repositories" / "tenant_repository.py": """
from config.database import get_connection

class TenantRepository:

    def get_all(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT TOP 100 tenant_id, tenant_name, tenant_code FROM tenant")
        rows = cur.fetchall()
        conn.close()
        return rows
""",
    BACKEND / "services" / "tenant_service.py": """
from repositories.tenant_repository import TenantRepository

class TenantService:

    def get_all(self):
        return TenantRepository().get_all()
""",
    BACKEND / "controllers" / "tenant_controller.py": """
from fastapi import APIRouter
from services.tenant_service import TenantService

router = APIRouter(prefix='/api/tenants', tags=['Tenants'])

@router.get('')
def get_tenants():
    rows = TenantService().get_all()

    return [
        {
            'tenant_id': str(r[0]),
            'tenant_name': r[1],
            'tenant_code': r[2]
        }
        for r in rows
    ]
""",
    BACKEND / "tests" / "test_tenant.py": "# Phase17\n"
}

for f, c in files.items():
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(c, encoding="utf-8")

app_file = BACKEND / "api" / "app.py"
app_text = app_file.read_text(encoding="utf-8")

if "tenant_controller" not in app_text:
    app_text = app_text.replace(
        "from controllers.auth_controller import router as auth_router",
        "from controllers.auth_controller import router as auth_router\nfrom controllers.tenant_controller import router as tenant_router"
    )

    app_text = app_text.replace(
        "app.include_router(auth_router)",
        "app.include_router(auth_router)\napp.include_router(tenant_router)"
    )

app_file.write_text(app_text, encoding="utf-8")

print("[SUCCESS] PHASE-17 INSTALLED")
