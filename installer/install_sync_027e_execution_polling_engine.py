from pathlib import Path

ROOT = Path(r'E:\Nexora')

EXEC_DIR = ROOT / 'store_agent' / 'execution'
EXEC_DIR.mkdir(parents=True, exist_ok=True)

(EXEC_DIR / 'execution_models.py').write_text('''class ExecutionModel:

    FIELDS = [
        "execution_id",
        "tenant_id",
        "store_id",
        "execution_type",
        "sync_mode",
        "execution_status",
        "total_tables",
        "completed_tables",
        "failed_tables"
    ]
''', encoding='utf-8')

(EXEC_DIR / 'execution_client.py').write_text('''import requests

class ExecutionClient:

    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def get_pending_execution(self, store_id):
        response = requests.get(
            f"{self.base_url}/api/sync/execution/pending/{store_id}",
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def start_execution(self, execution_id):
        response = requests.post(
            f"{self.base_url}/api/sync/execution/{execution_id}/start",
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def complete_execution(self, execution_id):
        response = requests.post(
            f"{self.base_url}/api/sync/execution/{execution_id}/complete",
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def fail_execution(self, execution_id, error_message):
        response = requests.post(
            f"{self.base_url}/api/sync/execution/{execution_id}/fail",
            json={"error_message": error_message},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
''', encoding='utf-8')

(EXEC_DIR / 'execution_polling_service.py').write_text('''from store_agent.execution.execution_client import ExecutionClient
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
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_execution_polling_engine.py').write_text('''def test_import():
    from store_agent.execution.execution_polling_service import ExecutionPollingService
    assert ExecutionPollingService is not None
''', encoding='utf-8')

print('SYNC-027E INSTALL COMPLETE')
