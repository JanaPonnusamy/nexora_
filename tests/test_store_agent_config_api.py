def test_import():
    from backend.modules.store_agent.config_service import get_configuration
    assert get_configuration is not None
