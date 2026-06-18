
# PHASE-20A Role Seed Runtime V1

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase20A_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = """
from config.database import get_connection
import uuid

class RoleRepository:

    def seed_roles(self):

        roles = [
            ('SUPER_ADMIN','Platform Control'),
            ('TENANT_ADMIN','Tenant Control'),
            ('STORE_ADMIN','Store Administration'),
            ('STORE_MANAGER','Store Operations'),
            ('STORE_USER','Standard User'),
            ('SYNC_OPERATOR','Sync Monitoring')
        ]

        conn = get_connection()
        cur = conn.cursor()

        inserted = 0

        for role_name, description in roles:

            cur.execute(
                'SELECT COUNT(*) FROM dbo.roles WHERE role_name = ?',
                role_name
            )

            if cur.fetchone()[0] > 0:
                continue

            cur.execute(\"\"\"
            INSERT INTO dbo.roles
            (
                role_id,
                role_name,
                description,
                is_active
            )
            VALUES
            (
                ?,?,?,1
            )
            \"\"\",
            str(uuid.uuid4()),
            role_name,
            description
            )

            inserted += 1

        conn.commit()
        conn.close()

        return inserted
"""
(BACKEND / "repositories" / "role_repository.py").write_text(repo_code, encoding="utf-8")

service_code = """
from repositories.role_repository import RoleRepository

class RoleService:

    def seed_roles(self):
        return RoleRepository().seed_roles()
"""
(BACKEND / "services" / "role_service.py").write_text(service_code, encoding="utf-8")

controller_code = """
from fastapi import APIRouter
from services.role_service import RoleService

router = APIRouter(prefix='/api/roles', tags=['Roles'])

@router.post('/seed')
def seed_roles():
    count = RoleService().seed_roles()

    return {
        'status':'success',
        'roles_created':count
    }
"""
(BACKEND / "controllers" / "role_controller.py").write_text(controller_code, encoding="utf-8")

app_file = BACKEND / "api" / "app.py"

if app_file.exists():
    txt = app_file.read_text(encoding="utf-8")

    if "role_controller" not in txt:
        txt += "\nfrom controllers.role_controller import router as role_router\n"
        txt += "\napp.include_router(role_router)\n"

    app_file.write_text(txt, encoding="utf-8")

print("[SUCCESS] PHASE-20A INSTALLED")
