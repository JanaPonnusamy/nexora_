def test_import():
    from backend.modules.sync.physical_table_creation_service import PhysicalTableCreationService
    assert PhysicalTableCreationService is not None
