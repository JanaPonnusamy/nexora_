
from store_agent.fernet_key_service import FernetKeyService

def test_fernet_key_service_exists():

    service = FernetKeyService()

    assert service is not None
