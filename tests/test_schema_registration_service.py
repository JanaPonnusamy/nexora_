from store_agent.schema_registration_service import SchemaRegistrationService

def test_registration_service_exists():
    service = SchemaRegistrationService()
    assert service is not None
