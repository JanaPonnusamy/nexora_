from store_agent.schema_sync_readiness import SchemaSyncReadinessCheck

def test_readiness_check():
    result = SchemaSyncReadinessCheck().check()

    assert result["ready"] is True
