# SYNC-013 Schema Payload Assembly Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync013_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

builder_code = '''
class SchemaPayloadAssembler:

    def assemble(self, store_id, database_name, catalog):

        return {
            "store_id": store_id,
            "database_name": database_name,
            "tables": catalog.get("tables", [])
        }
'''

test_code = '''
from store_agent.schema_payload_assembler import SchemaPayloadAssembler

def test_schema_payload_assembler():
    assembler = SchemaPayloadAssembler()

    payload = assembler.assemble(
        "STORE001",
        "DB001",
        {"tables":[]}
    )

    assert payload["store_id"] == "STORE001"
    assert payload["database_name"] == "DB001"
    assert "tables" in payload
'''

write_file(ROOT / "store_agent" / "schema_payload_assembler.py", builder_code)
write_file(ROOT / "tests" / "test_schema_payload_assembler.py", test_code)

print("=" * 80)
print("SYNC-013 INSTALL COMPLETE")
print("=" * 80)
