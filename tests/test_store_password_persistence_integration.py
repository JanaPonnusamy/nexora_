
from store_agent.store_password_persistence_integration import (
    StorePasswordPersistenceIntegration
)

def test_integration_exists():

    integration = (
        StorePasswordPersistenceIntegration()
    )

    result = integration.build(
        "STORE001",
        "Admin123"
    )

    assert result["encrypted_password"] is not None
