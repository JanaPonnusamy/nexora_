from pathlib import Path

ROOT = Path(r'E:\Nexora')

EXEC_DIR = ROOT / 'store_agent' / 'execution'
EXEC_DIR.mkdir(parents=True, exist_ok=True)

(EXEC_DIR / 'execution_context.py').write_text('''class ExecutionContext:

    def __init__(
        self,
        execution_id,
        tenant_id,
        store_id,
        execution_type,
        sync_mode
    ):
        self.execution_id = execution_id
        self.tenant_id = tenant_id
        self.store_id = store_id
        self.execution_type = execution_type
        self.sync_mode = sync_mode
''', encoding='utf-8')

(EXEC_DIR / 'execution_result.py').write_text('''class ExecutionResult:

    def __init__(
        self,
        success=True,
        message='',
        tables_processed=0,
        rows_processed=0
    ):
        self.success = success
        self.message = message
        self.tables_processed = tables_processed
        self.rows_processed = rows_processed
''', encoding='utf-8')

(EXEC_DIR / 'execution_dispatcher.py').write_text('''from store_agent.execution.execution_result import ExecutionResult

class ExecutionDispatcher:

    def dispatch(self, execution):

        execution_type = execution.execution_type

        if execution_type == 'FULL_SYNC':
            return self.execute_full_sync()

        if execution_type == 'TABLE_SYNC':
            return self.execute_table_sync()

        if execution_type == 'CATALOG_REFRESH':
            return self.execute_catalog_refresh()

        raise Exception(
            f'Unsupported execution type: {execution_type}'
        )

    def execute_full_sync(self):
        return ExecutionResult(
            True,
            'FULL_SYNC routed'
        )

    def execute_table_sync(self):
        return ExecutionResult(
            True,
            'TABLE_SYNC routed'
        )

    def execute_catalog_refresh(self):
        return ExecutionResult(
            True,
            'CATALOG_REFRESH routed'
        )
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_execution_dispatcher.py').write_text('''from store_agent.execution.execution_dispatcher import ExecutionDispatcher
from store_agent.execution.execution_context import ExecutionContext

def test_dispatcher():

    dispatcher = ExecutionDispatcher()

    result = dispatcher.dispatch(
        ExecutionContext(
            '1',
            '1',
            '1',
            'FULL_SYNC',
            'MANUAL'
        )
    )

    assert result.success is True
''', encoding='utf-8')

print('SYNC-027E-B INSTALL COMPLETE')
