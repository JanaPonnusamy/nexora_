
from store_agent.sql_connection_verification_service import (
    SqlConnectionVerificationService
)

def test_verification_service_exists():
    service = SqlConnectionVerificationService()
    assert service is not None
