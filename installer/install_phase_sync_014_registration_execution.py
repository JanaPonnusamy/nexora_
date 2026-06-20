# SYNC-014 HO Registration Execution Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync014_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

service_code = '''
from store_agent.sync_client import SyncClient

class SchemaRegistrationExecutor:

    def execute(self, api_url, payload):
        return SyncClient().post_schema(
            api_url,
            payload
        )
'''

test_code = '''
from store_agent.schema_registration_executor import SchemaRegistrationExecutor

def test_schema_registration_executor():
    executor = SchemaRegistrationExecutor()
    assert executor is not None
'''

write_file(ROOT / "store_agent" / "schema_registration_executor.py", service_code)
write_file(ROOT / "tests" / "test_schema_registration_executor.py", test_code)

print("=" * 80)
print("SYNC-014 INSTALL COMPLETE")
print("=" * 80)
