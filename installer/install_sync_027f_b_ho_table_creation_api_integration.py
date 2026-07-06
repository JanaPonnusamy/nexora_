from pathlib import Path

ROOT = Path(r'E:\Nexora')

EXEC_DIR = ROOT / 'store_agent' / 'execution'
EXEC_DIR.mkdir(parents=True, exist_ok=True)

(EXEC_DIR / 'ho_table_creation_client.py').write_text('''import requests

class HOTableCreationClient:

    def __init__(self, base_url='http://127.0.0.1:8000'):
        self.base_url = base_url.rstrip('/')

    def build(self, execution_id):

        response = requests.post(
            f'{self.base_url}/api/sync/table-creation/build/{execution_id}',
            timeout=120
        )

        response.raise_for_status()

        return response.json()
''', encoding='utf-8')

ORCH_DIR = ROOT / 'store_agent' / 'orchestrator'

(ORCH_DIR / 'table_creation_orchestrator.py').write_text('''from store_agent.execution.ho_table_creation_client import HOTableCreationClient

class TableCreationOrchestrator:

    def execute(self, execution_id):

        result = (
            HOTableCreationClient()
            .build(execution_id)
        )

        return {
            "success": True,
            "result": result
        }
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_ho_table_creation_integration.py').write_text('''from store_agent.execution.ho_table_creation_client import HOTableCreationClient

def test_import():
    assert HOTableCreationClient is not None
''', encoding='utf-8')

print('SYNC-027F-B INSTALL COMPLETE')
