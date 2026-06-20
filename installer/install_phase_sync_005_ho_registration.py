# SYNC-005 HO Schema Registration Integration Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync005_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

engine_code = """
from store_agent.schema_sync_engine import SchemaSyncEngine
from store_agent.sync_client import SyncClient

class SchemaRegistrationService:

    def register(self, store_id, database_name, api_url):
        payload = SchemaSyncEngine().build_payload(
            store_id,
            database_name
        )

        return SyncClient().post_schema(
            api_url,
            payload
        )
"""

test_code = """
from store_agent.schema_registration_service import SchemaRegistrationService

def test_registration_service_exists():
    service = SchemaRegistrationService()
    assert service is not None
"""

write_file(ROOT / "store_agent" / "schema_registration_service.py", engine_code)
write_file(ROOT / "tests" / "test_schema_registration_service.py", test_code)

print("=" * 80)
print("SYNC-005 INSTALL COMPLETE")
print("=" * 80)
