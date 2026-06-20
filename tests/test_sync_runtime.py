from store_agent.schema_registration_service import SchemaRegistrationService

def test_runtime_dependencies():
    service = SchemaRegistrationService()
    assert service is not None
