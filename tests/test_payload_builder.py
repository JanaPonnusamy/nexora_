from store_agent.payload_builder import PayloadBuilder

def test_payload_builder():
    builder = PayloadBuilder()

    payload = builder.build(
        "STORE-001",
        "PHARMACY_DB",
        []
    )

    assert payload["store_id"] == "STORE-001"
    assert payload["database_name"] == "PHARMACY_DB"
    assert isinstance(payload["tables"], list)
