from store_agent.runtime_configuration_loader import (
    RuntimeConfigurationLoader
)

class StoreAgentBootstrapService:

    def bootstrap(self, config_url):

        runtime_config = (
            RuntimeConfigurationLoader()
            .load(config_url)
        )

        return {
            "status": "ready",
            "runtime_config": runtime_config
        }
