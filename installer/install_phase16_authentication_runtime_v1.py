"""
NEXORA
PHASE-16
Authentication Runtime V1 Installer
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase16_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

files = {
    BACKEND / "dtos" / "login_request.py": "from pydantic import BaseModel\n\nclass LoginRequest(BaseModel):\n    username:str\n    password:str\n",
    BACKEND / "dtos" / "login_response.py": "from pydantic import BaseModel\n\nclass LoginResponse(BaseModel):\n    token:str\n    username:str\n",
    BACKEND / "repositories" / "user_repository.py": "class UserRepository:\n    def validate_user(self,u,p):\n        return u=='admin' and p=='Admin123'\n",
    BACKEND / "services" / "auth_service.py": "from repositories.user_repository import UserRepository\n\nclass AuthService:\n    def login(self,u,p):\n        if UserRepository().validate_user(u,p):\n            return {'token':'NEXORA_DEV_TOKEN','username':u}\n        return None\n",
    BACKEND / "controllers" / "auth_controller.py": "from fastapi import APIRouter\nfrom dtos.login_request import LoginRequest\nfrom services.auth_service import AuthService\n\nrouter=APIRouter(prefix='/api/auth')\n\n@router.post('/login')\ndef login(req:LoginRequest):\n    r=AuthService().login(req.username,req.password)\n    return r if r else {'error':'Invalid Username Or Password'}\n\n@router.get('/me')\ndef me():\n    return {'username':'admin','role':'Administrator'}\n"
}

for f,c in files.items():
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(c, encoding="utf-8")

app = """from fastapi import FastAPI
from config.database import get_connection
from controllers.auth_controller import router as auth_router

app = FastAPI(title='NEXORA API')
app.include_router(auth_router)

@app.get('/health')
def health():
    return {'status':'healthy'}

@app.get('/health/db')
def health_db():
    try:
        conn=get_connection()
        conn.close()
        return {'status':'healthy','database':'connected'}
    except Exception as ex:
        return {'status':'failed','error':str(ex)}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
"""
(BACKEND/"api"/"app.py").write_text(app, encoding="utf-8")

print("[SUCCESS] PHASE-16 INSTALLED")
