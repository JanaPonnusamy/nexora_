from store_agent.store_agent_config_client import StoreAgentConfigClient

def test_client_exists():
    client = StoreAgentConfigClient()
    assert client is not None
