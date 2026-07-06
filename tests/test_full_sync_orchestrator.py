from store_agent.orchestrator.full_sync_orchestrator import FullSyncOrchestrator

def test_orchestrator_import():
    assert FullSyncOrchestrator() is not None
