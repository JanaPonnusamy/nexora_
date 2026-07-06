def test_import():
    from backend.modules.sync.ddl_creation_service import DDLCreationService
    assert DDLCreationService is not None
