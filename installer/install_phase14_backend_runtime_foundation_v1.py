
"""
NEXORA
PHASE-14
Backend Runtime Foundation V1 Installer
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

FILES = {
    BACKEND / "api" / "app.py": """from fastapi import FastAPI

app = FastAPI(title='NEXORA API')

@app.get('/health')
def health():
    return {'status': 'healthy'}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
""",
    BACKEND / "config" / "settings.py": "APP_NAME='NEXORA'\n",
    BACKEND / "config" / "database.py": "DATABASE_CONNECTION=''\n",
    BACKEND / "config" / "logger.py": "import logging\n",
    BACKEND / "middleware" / "exception_middleware.py": "",
    BACKEND / "middleware" / "request_middleware.py": ""
}

print("[INFO] PHASE-14 INSTALL STARTED")

if BACKEND.exists():
    backup_dir = ROOT / "backup" / f"phase14_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copytree(BACKEND, backup_dir, dirs_exist_ok=True)

for file_path, content in FILES.items():
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')
    print(f"[UPDATE] {file_path}")

print("[SUCCESS] PHASE-14 INSTALLED")
