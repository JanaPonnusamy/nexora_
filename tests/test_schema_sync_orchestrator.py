from store_agent.schema_sync_orchestrator import SchemaSyncOrchestrator

def test_schema_sync_orchestrator():
    orchestrator = SchemaSyncOrchestrator()
    assert orchestrator.run() is True
