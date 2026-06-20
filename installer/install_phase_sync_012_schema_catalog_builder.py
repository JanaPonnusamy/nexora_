# SYNC-012 Unified Schema Catalog Builder Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync012_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

builder_code = '''
class SchemaCatalogBuilder:

    def build(self, tables, columns, primary_keys, identity_columns):

        return {
            "tables": tables,
            "columns": columns,
            "primary_keys": primary_keys,
            "identity_columns": identity_columns
        }
'''

test_code = '''
from store_agent.schema_catalog_builder import SchemaCatalogBuilder

def test_schema_catalog_builder():
    builder = SchemaCatalogBuilder()

    result = builder.build([], [], [], [])

    assert "tables" in result
    assert "columns" in result
    assert "primary_keys" in result
    assert "identity_columns" in result
'''

write_file(ROOT / "store_agent" / "schema_catalog_builder.py", builder_code)
write_file(ROOT / "tests" / "test_schema_catalog_builder.py", test_code)

print("=" * 80)
print("SYNC-012 INSTALL COMPLETE")
print("=" * 80)
