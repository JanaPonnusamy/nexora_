class ExecutionContext:

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
