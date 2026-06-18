"""
PHASE-20A REPAIR-01
Router Registration Fix
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

backup_dir = ROOT / "backup" / f"phase20A_repair01_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

app_code = """from fastapi import FastAPI

from config.database import get_connection

from controllers.auth_controller import router as auth_router
from controllers.tenant_controller import router as tenant_router
from controllers.store_controller import router as store_router
from controllers.role_controller import router as role_router

app = FastAPI(title='NEXORA API')

app.include_router(auth_router)
app.include_router(tenant_router)
app.include_router(store_router)
app.include_router(role_router)

@app.get('/health')
def health():
    return {'status':'healthy'}

@app.get('/health/db')
def health_db():
    try:
        conn = get_connection()
        conn.close()
        return {'status':'healthy','database':'connected'}
    except Exception as ex:
        return {'status':'failed','error':str(ex)}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
"""

(BACKEND / "api" / "app.py").write_text(app_code, encoding="utf-8")

print("[SUCCESS] PHASE-20A REPAIR-01 INSTALLED")
