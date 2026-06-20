# SYNC-004 Schema Payload Integration Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync004_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

runtime_code = """
from schema_scanner import SchemaScanner
from payload_builder import PayloadBuilder

class SchemaSyncEngine:

    def build_payload(self, store_id, database_name):
        scan_result = SchemaScanner().scan()

        return PayloadBuilder().build(
            store_id,
            database_name,
            scan_result.get("tables", [])
        )
"""

test_code = """
from store_agent.schema_sync_engine import SchemaSyncEngine

def test_payload_generation():
    engine = SchemaSyncEngine()

    payload = engine.build_payload(
        "STORE001",
        "DB001"
    )

    assert payload["store_id"] == "STORE001"
    assert payload["database_name"] == "DB001"
"""

write_file(ROOT / "store_agent" / "schema_sync_engine.py", runtime_code)
write_file(ROOT / "tests" / "test_schema_sync_engine.py", test_code)

print("=" * 80)
print("SYNC-004 INSTALL COMPLETE")
print("=" * 80)
