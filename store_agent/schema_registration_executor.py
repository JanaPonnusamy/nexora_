from store_agent.sync_client import SyncClient

class SchemaRegistrationExecutor:

    def execute(self, api_url, payload):
        return SyncClient().post_schema(
            api_url,
            payload
        )
