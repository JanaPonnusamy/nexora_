
from store_agent.store_agent_config_decryption_service import (
    StoreAgentConfigDecryptionService
)

def test_decryption_service_exists():
    service = StoreAgentConfigDecryptionService()
    assert service is not None
