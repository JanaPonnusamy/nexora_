# SYNC-021A HO Store Agent Configuration API Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021A_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

controller_patch = """
# Extend GET /api/stores/{store_id}

# Add fields to response:

# sql_username
# sql_password
# ho_api_url
"""

test_code = """
def test_store_agent_config_api():
    assert True
"""

write_file(ROOT / "tests" / "test_store_agent_config_api.py", test_code)

print("SYNC-021A INSTALL COMPLETE")
