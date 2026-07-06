def test_import():
    from backend.modules.sync.ddl_executor_service import DDLExecutorService
    assert DDLExecutorService is not None
