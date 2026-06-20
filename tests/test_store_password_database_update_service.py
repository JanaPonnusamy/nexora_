
from store_agent.store_password_database_update_service import (
    StorePasswordDatabaseUpdateService
)

def test_update_service_exists():

    service = StorePasswordDatabaseUpdateService()

    payload = service.build_update_payload(
        "STORE001",
        b"encrypted"
    )

    assert payload["store_id"] == "STORE001"
