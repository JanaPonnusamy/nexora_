from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader

def test_loader_exists():
    loader = RuntimeConfigurationLoader()
    assert loader is not None
