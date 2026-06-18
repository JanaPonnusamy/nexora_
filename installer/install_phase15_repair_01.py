
"""
NEXORA
PHASE-15 REPAIR-1
Complete app.py regeneration
No manual editing required
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

APP_CONTENT = """from fastapi import FastAPI
from config.database import get_connection

app = FastAPI(title='NEXORA API')

@app.get('/health')
def health():
    return {'status': 'healthy'}

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

backup_dir = ROOT / "backup" / f"phase15_repair_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if BACKEND.exists():
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

app_file = BACKEND / "api" / "app.py"
app_file.write_text(APP_CONTENT, encoding="utf-8")

print("[SUCCESS] PHASE-15 REPAIR APPLIED")
print(app_file)
