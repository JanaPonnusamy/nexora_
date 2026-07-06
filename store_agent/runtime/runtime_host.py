from store_agent.runtime.runtime_bootstrap import RuntimeBootstrap
from store_agent.runtime.runtime_ready_service import RuntimeReadyService
from store_agent.runtime.store_agent_runtime import StoreAgentRuntime

class RuntimeHost:

    def start(self):

        bootstrap_result = (
            RuntimeBootstrap()
            .bootstrap()
        )

        ready_result = (
            RuntimeReadyService()
            .build(
                bootstrap_result["verification"]
            )
        )

        if not ready_result["runtime_ready"]:
            raise RuntimeError(
                "Runtime bootstrap failed"
            )

        StoreAgentRuntime().run_forever()
