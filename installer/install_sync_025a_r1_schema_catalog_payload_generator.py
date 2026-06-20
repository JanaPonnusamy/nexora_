"""
SYNC-025A-R1
Column-Level Schema Catalog Payload Generator
"""

from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent.parent

SERVICE_FILE = ROOT / "store_agent" / "services" / "schema_catalog_payload_generator.py"
RUNNER_FILE = ROOT / "store_agent" / "run_schema_catalog_payload_generator.py"

SERVICE_CODE = """
import json
import uuid
from datetime import datetime, UTC
from pathlib import Path

from store_agent.config import STORE_ID

class SchemaCatalogPayloadGenerator:

    def __init__(self):
        self.base_path = Path(__file__).resolve().parent.parent
        self.schema_path = self.base_path / "schema"

    def generate(self):

        source_file = self.schema_path / "schema_column_snapshot.json"

        columns = json.loads(
            source_file.read_text(encoding="utf-8")
        )

        now_utc = datetime.now(UTC).isoformat()

        payload = []

        for row in columns:

            payload.append({
                "catalog_id": str(uuid.uuid4()),
                "schema_name": row["schema_name"],
                "table_name": row["table_name"],
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "max_length": row["max_length"],
                "precision_value": row["precision_value"],
                "scale_value": row["scale_value"],
                "is_nullable": row["is_nullable"],
                "is_identity": row["is_identity"],
                "is_primary_key": row["is_primary_key"],
                "ordinal_position": row["ordinal_position"],
                "first_discovered_store_id": STORE_ID,
                "first_discovered_at": now_utc,
                "last_discovered_at": now_utc,
                "is_active": True
            })

        output_file = self.schema_path / "schema_catalog_payload.json"

        output_file.write_text(
            json.dumps(payload, indent=4),
            encoding="utf-8"
        )

        return {
            "payload_rows": len(payload),
            "output_file": str(output_file)
        }
"""

RUNNER_CODE = """
from store_agent.services.schema_catalog_payload_generator import (
    SchemaCatalogPayloadGenerator
)

def main():
    result = SchemaCatalogPayloadGenerator().generate()

    print("[OK] Schema Catalog Payload Generated")
    print(f"ROWS     : {result['payload_rows']}")
    print(f"OUTPUT   : {result['output_file']}")

if __name__ == "__main__":
    main()
"""

def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\\n", encoding="utf-8")

write_file(SERVICE_FILE, SERVICE_CODE)
write_file(RUNNER_FILE, RUNNER_CODE)

print("SYNC-025A-R1 installer completed")
