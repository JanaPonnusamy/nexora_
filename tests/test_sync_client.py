from store_agent.sync_client import SyncClient

def test_sync_client_exists():
    client = SyncClient()
    assert client is not None
