"""
SYNC-025A
install_sync_025a_sync_schema_catalog_population_generator.py
"""

from pathlib import Path
import json
import textwrap

ROOT = Path(__file__).resolve().parent.parent

SERVICE_FILE = ROOT / "store_agent" / "services" / "sync_schema_catalog_generator.py"
RUNNER_FILE = ROOT / "store_agent" / "run_sync_schema_catalog_population.py"

SERVICE_CODE = """
from pathlib import Path
import json

class SyncSchemaCatalogGenerator:

    def __init__(self):
        self.base_path = Path(__file__).resolve().parent.parent
        self.schema_path = self.base_path / "schema"

    def generate(self):

        snapshot_file = self.schema_path / "schema_snapshot.json"
        classification_file = self.schema_path / "schema_classification.json"
        output_file = self.schema_path / "schema_catalog_payload.json"

        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
        classification = json.loads(classification_file.read_text(encoding="utf-8"))

        store_id = (
            snapshot.get("store_id")
            or snapshot.get("storeId")
            or snapshot.get("STORE_ID")
        )

        rows = []

        tables = snapshot.get("tables", [])

        classification_lookup = {}

        if isinstance(classification, dict):

            if "tables" in classification:
                source = classification["tables"]
            else:
                source = classification

            if isinstance(source, list):
                for item in source:
                    table_name = (
                        item.get("table_name")
                        or item.get("table")
                        or item.get("name")
                    )
                    if table_name:
                        classification_lookup[table_name.lower()] = item
            elif isinstance(source, dict):
                for key, value in source.items():
                    classification_lookup[key.lower()] = value

        for table in tables:

            table_name = (
                table.get("table_name")
                or table.get("name")
            )

            schema_name = (
                table.get("schema_name")
                or table.get("schema")
                or "dbo"
            )

            row_count = table.get("row_count", 0)

            classification_value = "UNCLASSIFIED"

            match = classification_lookup.get(str(table_name).lower())

            if isinstance(match, dict):
                classification_value = (
                    match.get("classification")
                    or match.get("category")
                    or "UNCLASSIFIED"
                )
            elif isinstance(match, str):
                classification_value = match

            rows.append({
                "store_id": store_id,
                "schema_name": schema_name,
                "table_name": table_name,
                "classification": classification_value,
                "row_count": row_count,
                "is_selected": False,
                "approval_status": "PENDING"
            })

        output_file.write_text(
            json.dumps(rows, indent=4),
            encoding="utf-8"
        )

        return {
            "payload_rows": len(rows),
            "output_file": str(output_file)
        }
"""

RUNNER_CODE = """
from services.sync_schema_catalog_generator import SyncSchemaCatalogGenerator

def main():
    result = SyncSchemaCatalogGenerator().generate()
    print(result)

if __name__ == "__main__":
    main()
"""

def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\\n", encoding="utf-8")

write_file(SERVICE_FILE, SERVICE_CODE)
write_file(RUNNER_FILE, RUNNER_CODE)

print("SYNC-025A installer completed")
