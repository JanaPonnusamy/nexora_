import time
import requests

from store_agent.config import STORE_ID, HO_API_URL
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.sync_runtime_orchestrator import SyncRuntimeOrchestrator

TENANT = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"


def main():
    cfg_url = f"{HO_API_URL}/api/stores/{STORE_ID}/agent-config"
    runtime_config = RuntimeConfigurationLoader().load(cfg_url)
    ctx = RuntimeContextFactory().create(runtime_config)

    # Clear any stale pending tasks so each cycle processes exactly one.
    requests.post(f"{HO_API_URL}/api/sync/control",
                  json={"store_ids": [STORE_ID], "action": "STOP"}, timeout=30)

    for i in (1, 2):
        print(f"\n========== TRIGGER SYNC {i} ==========", flush=True)
        requests.post(f"{HO_API_URL}/api/sync/tasks/create",
                      json={"tenant_id": TENANT, "store_id": STORE_ID,
                            "total_tables": 9}, timeout=30)
        conn = RuntimeSqlConnectionService().connect(ctx)
        orch = SyncRuntimeOrchestrator(connection=conn, ho_api_url=HO_API_URL,
                                       store_id=STORE_ID)
        started = time.time()
        result = orch.run_cycle()
        conn.close()
        print(f"SYNC {i} DONE in {time.time()-started:.1f}s "
              f"tasks={result['tasks_processed']}", flush=True)
        time.sleep(1)

    print("\n========== ALL SYNCS COMPLETE ==========", flush=True)


if __name__ == "__main__":
    main()
