from store_agent.runtime_context import StoreAgentRuntimeContext

class RuntimeContextFactory:

    def create(self, runtime_config):

        return StoreAgentRuntimeContext(
            runtime_config
        )
