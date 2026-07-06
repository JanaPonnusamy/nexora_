from pathlib import Path

ROOT = Path(r'E:\Nexora')

ORCH_DIR = ROOT / 'store_agent' / 'orchestrator'
ORCH_DIR.mkdir(parents=True, exist_ok=True)

(ORCH_DIR / 'table_creation_orchestrator.py').write_text('''from store_agent.runtime.metadata_runtime_reader import MetadataRuntimeReader

class TableCreationOrchestrator:

    def execute(self):

        tables = MetadataRuntimeReader().get_tables()

        return {
            "success": True,
            "tables_found": len(tables),
            "tables": [
                x["table_name"]
                for x in tables
            ]
        }
''', encoding='utf-8')

(ORCH_DIR / 'table_creation_result.py').write_text('''class TableCreationResult:

    def __init__(
        self,
        success=True,
        tables_created=0,
        columns_created=0,
        message=''
    ):
        self.success = success
        self.tables_created = tables_created
        self.columns_created = columns_created
        self.message = message
''', encoding='utf-8')

full_sync = ROOT / 'store_agent' / 'orchestrator' / 'full_sync_orchestrator.py'

if full_sync.exists():
    full_sync.write_text('''from store_agent.runtime.metadata_runtime_reader import MetadataRuntimeReader
from store_agent.execution.execution_result import ExecutionResult
from store_agent.orchestrator.table_creation_orchestrator import TableCreationOrchestrator

class FullSyncOrchestrator:

    def execute(self, execution):

        table_result = (
            TableCreationOrchestrator()
            .execute()
        )

        tables = MetadataRuntimeReader().get_tables()

        return ExecutionResult(
            success=True,
            message='FULL_SYNC orchestrated',
            tables_processed=len(tables),
            rows_processed=0
        )
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_table_creation_orchestrator.py').write_text('''from store_agent.orchestrator.table_creation_orchestrator import TableCreationOrchestrator

def test_import():
    assert TableCreationOrchestrator() is not None
''', encoding='utf-8')

print('SYNC-027F-A INSTALL COMPLETE')
