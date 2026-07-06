from store_agent.runtime.metadata_runtime_reader import MetadataRuntimeReader
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
