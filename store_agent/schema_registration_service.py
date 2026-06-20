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
