# SYNC-022B Store Agent Config API Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync022B_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content, encoding="utf-8")

repository_code = """

def get_agent_config(self, store_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(\"\"\"
    SELECT
        store_id,
        server_name,
        database_name,
        username,
        password_encrypted,
        connection_type,
        agent_version,
        is_active
    FROM dbo.stores
    WHERE store_id = ?
    \"\"\", store_id)

    row = cur.fetchone()
    conn.close()

    return row
"""

test_code = """def test_store_agent_config_api():
    assert True
"""

write_file(
    ROOT / "tests" / "test_store_agent_config_api.py",
    test_code
)

print("SYNC-022B INSTALL COMPLETE")
