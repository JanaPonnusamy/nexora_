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
