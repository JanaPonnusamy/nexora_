from store_agent.execution.execution_result import ExecutionResult

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
