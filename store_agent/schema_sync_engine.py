from store_agent.schema_scanner import SchemaScanner
from store_agent.payload_builder import PayloadBuilder

class SchemaSyncEngine:

    def build_payload(self, store_id, database_name):
        scan_result = SchemaScanner().scan()

        return PayloadBuilder().build(
            store_id,
            database_name,
            scan_result.get("tables", [])
        )
