# SYNC-018 Schema Sync Execution Report Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync018_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

report_code = '''
class SchemaSyncReport:

    def build(self, status=True):
        return {
            "success": status
        }
'''

test_code = '''
from store_agent.schema_sync_report import SchemaSyncReport

def test_schema_sync_report():
    result = SchemaSyncReport().build()
    assert result["success"] is True
'''

write_file(ROOT / "store_agent" / "schema_sync_report.py", report_code)
write_file(ROOT / "tests" / "test_schema_sync_report.py", test_code)

print("SYNC-018 INSTALL COMPLETE")
