from store_agent.execution.execution_client import ExecutionClient
from store_agent.config_cache.configuration_cache_service import ConfigurationCacheService

class ExecutionPollingService:

    def __init__(self):
        self.client = ExecutionClient()

    def _get_store_id(self):

        config = ConfigurationCacheService().load_configuration(
            "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"
        )

        if config:
            return config["store_id"]

        return "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"

    def get_pending_execution(self):
        return self.client.get_pending_execution(
            self._get_store_id()
        )

    def start_execution(self, execution_id):
        return self.client.start_execution(execution_id)

    def complete_execution(self, execution_id):
        return self.client.complete_execution(execution_id)

    def fail_execution(self, execution_id, error_message):
        return self.client.fail_execution(
            execution_id,
            error_message
        )
