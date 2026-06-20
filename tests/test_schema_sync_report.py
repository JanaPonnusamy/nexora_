from store_agent.schema_sync_report import SchemaSyncReport

def test_schema_sync_report():
    result = SchemaSyncReport().build()
    assert result["success"] is True
