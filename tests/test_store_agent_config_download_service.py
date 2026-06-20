
from store_agent.store_agent_config_download_service import (
    StoreAgentConfigDownloadService
)

def test_download_service_exists():
    service = StoreAgentConfigDownloadService()
    assert service is not None
