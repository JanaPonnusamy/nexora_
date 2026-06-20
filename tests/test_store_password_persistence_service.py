
from store_agent.store_password_persistence_service import (
    StorePasswordPersistenceService
)

def test_persistence_service_exists():

    service = StorePasswordPersistenceService()

    sql, params = service.create_update_request(
        "STORE001",
        b"encrypted"
    )

    assert "UPDATE dbo.stores" in sql
