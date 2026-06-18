# PHASE-19AB Authentication Database Runtime V1
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r'E:\Nexora')
BACKEND = ROOT / 'backend'

backup_dir = ROOT / 'backup' / f"phase19AB_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

repo_code = '''
from config.database import get_connection

class UserRepository:

    def get_user_by_username(self, username):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT user_id,username,password_hash,first_name,is_platform_user,is_active
        FROM dbo.users
        WHERE username = ?
        """, username)
        row = cur.fetchone()
        conn.close()
        return row

    def update_last_login(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.users
        SET last_login = GETDATE()
        WHERE user_id = ?
        """, user_id)
        conn.commit()
        conn.close()
'''
(BACKEND / 'repositories' / 'user_repository.py').write_text(repo_code, encoding='utf-8')

service_code = '''
import bcrypt
from repositories.user_repository import UserRepository

class AuthService:

    def login(self, username, password):
        repo = UserRepository()
        user = repo.get_user_by_username(username)

        if not user:
            return None

        if not bool(user[5]):
            return None

        if not bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
            return None

        repo.update_last_login(user[0])

        return {
            "user_id": str(user[0]),
            "username": user[1],
            "first_name": user[3],
            "is_platform_user": bool(user[4]),
            "is_active": bool(user[5])
        }
'''
(BACKEND / 'services' / 'auth_service.py').write_text(service_code, encoding='utf-8')

controller_code = '''
from fastapi import APIRouter
from dtos.login_request import LoginRequest
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

_current_user = None

@router.post("/login")
def login(req: LoginRequest):
    global _current_user

    user = AuthService().login(req.username, req.password)

    if not user:
        return {"error":"Invalid Username Or Password"}

    _current_user = user
    return user

@router.get("/me")
def me():
    return _current_user if _current_user else {"error":"Not Logged In"}
'''
(BACKEND / 'controllers' / 'auth_controller.py').write_text(controller_code, encoding='utf-8')

print('[SUCCESS] PHASE-19AB INSTALLED')
