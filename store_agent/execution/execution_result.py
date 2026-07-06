class ExecutionResult:

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
