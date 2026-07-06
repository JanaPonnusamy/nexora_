from store_agent import config
from store_agent.config import STORE_ID
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.sync_runtime_orchestrator import SyncRuntimeOrchestrator


def main():
    ho_url = config.active_ho_url()
    config_url = f"{ho_url}/api/stores/{STORE_ID}/agent-config"

    runtime_config = RuntimeConfigurationLoader().load(config_url)
    runtime_context = RuntimeContextFactory().create(runtime_config)
    connection = RuntimeSqlConnectionService().connect(runtime_context)

    orchestrator = SyncRuntimeOrchestrator(
        connection=connection,
        ho_api_url=ho_url,
        store_id=STORE_ID,
    )

    result = orchestrator.run_cycle()

    print("[OK] Sync Runtime Cycle Complete")
    print(f"TASKS PROCESSED : {result['tasks_processed']}")
    for item in result["results"]:
        print(f"  TASK {item['task_id']} -> {item['status']}")


if __name__ == "__main__":
    main()
