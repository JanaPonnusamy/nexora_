from store_agent.store_agent_config_client import StoreAgentConfigClient
from store_agent.store_agent_config_contract import StoreAgentConfigContract

class StoreAgentConfigurationService:

    def get_runtime_config(self, url):

        config = StoreAgentConfigClient().get_config(url)

        for field in StoreAgentConfigContract.REQUIRED_FIELDS:
            if field not in config:
                raise ValueError(f"Missing configuration field: {field}")

        return config
