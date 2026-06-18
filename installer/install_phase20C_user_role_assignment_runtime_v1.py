# PHASE-20C User Role Assignment Runtime V1
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r'E:\Nexora')
BACKEND = ROOT / 'backend'

backup_dir = ROOT / 'backup' / f"phase20C_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class UserRoleRepository:

    def seed_superadmin_assignment(self):
        user_id = '4055B2C9-30E8-4062-9D52-666EF0769D4B'
        role_id = '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7'

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT TOP 1 store_id FROM dbo.stores ORDER BY store_code")
        store = cur.fetchone()

        if not store:
            conn.close()
            return 0

        store_id = str(store[0])

        cur.execute("SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?", user_id, store_id, role_id)

        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)", user_id, store_id, role_id)
            conn.commit()
            conn.close()
            return 1

        conn.close()
        return 0

    def get_user_roles(self, user_id):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT r.role_id,r.role_name,s.store_id,s.store_code,s.store_name
        FROM dbo.user_store_roles usr
        INNER JOIN dbo.roles r ON usr.role_id=r.role_id
        INNER JOIN dbo.stores s ON usr.store_id=s.store_id
        WHERE usr.user_id=?
        """, user_id)

        rows = cur.fetchall()
        conn.close()
        return rows
'''
(BACKEND / 'repositories' / 'user_role_repository.py').write_text(repo_code, encoding='utf-8')

service_code = '''
from repositories.user_role_repository import UserRoleRepository

class UserRoleService:

    def seed(self):
        return UserRoleRepository().seed_superadmin_assignment()

    def get_roles(self, user_id):
        rows = UserRoleRepository().get_user_roles(user_id)

        return [{
            "role_id": str(r[0]),
            "role_name": r[1],
            "store_id": str(r[2]),
            "store_code": r[3],
            "store_name": r[4]
        } for r in rows]
'''
(BACKEND / 'services' / 'user_role_service.py').write_text(service_code, encoding='utf-8')

controller_code = '''
from fastapi import APIRouter
from services.user_role_service import UserRoleService

router = APIRouter(prefix="/api/user-roles", tags=["User Roles"])

@router.post("/seed")
def seed():
    count = UserRoleService().seed()
    return {"status":"success","assignments_created":count}

@router.get("/user/{user_id}")
def get_user_roles(user_id:str):
    return UserRoleService().get_roles(user_id)
'''
(BACKEND / 'controllers' / 'user_role_controller.py').write_text(controller_code, encoding='utf-8')

app_path = BACKEND / 'api' / 'app.py'
txt = app_path.read_text(encoding='utf-8')

if 'user_role_router' not in txt:
    txt = txt.replace(
        'from controllers.role_controller import router as role_router',
        'from controllers.role_controller import router as role_router\nfrom controllers.user_role_controller import router as user_role_router'
    )
    txt = txt.replace(
        'app.include_router(role_router)',
        'app.include_router(role_router)\napp.include_router(user_role_router)'
    )

app_path.write_text(txt, encoding='utf-8')

print('[SUCCESS] PHASE-20C INSTALLED')
