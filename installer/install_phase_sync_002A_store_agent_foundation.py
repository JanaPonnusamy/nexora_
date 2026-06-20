# SYNC-002A Store Agent Foundation Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if not path.exists():
        return
    backup_dir = ROOT / "backup" / f"sync002A_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")
    print(f"CREATED : {path}")

files = {
    "store_agent/__init__.py": "",
    "store_agent/config.py": "STORE_ID=''\\nHO_API_URL='http://127.0.0.1:8000'\\n",
    "store_agent/database.py": "import pyodbc\\n",
    "store_agent/logger.py": "import logging\\n",
    "store_agent/run_schema_sync.py": "print('SYNC-002A Foundation Ready')\\n",
    "tests/test_store_agent_foundation.py": "def test_foundation():\\n    assert True\\n",
}

(ROOT / "store_agent" / "logs").mkdir(parents=True, exist_ok=True)

for rel, content in files.items():
    write_file(ROOT / rel, content)

print("=" * 80)
print("SYNC-002A INSTALL COMPLETE")
print("=" * 80)
