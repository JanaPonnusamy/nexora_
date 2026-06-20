from store_agent.store_agent_bootstrap_service import (
    StoreAgentBootstrapService
)

def test_bootstrap_service_exists():
    service = StoreAgentBootstrapService()
    assert service is not None
