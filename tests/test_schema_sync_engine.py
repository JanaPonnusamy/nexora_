from store_agent.schema_sync_engine import SchemaSyncEngine

def test_payload_generation():
    engine = SchemaSyncEngine()

    payload = engine.build_payload(
        "STORE001",
        "DB001"
    )

    assert payload["store_id"] == "STORE001"
    assert payload["database_name"] == "DB001"
