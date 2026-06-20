from store_agent.runtime_health_check import RuntimeHealthCheck

def test_runtime_health_check():
    result = RuntimeHealthCheck().check()
    assert result["status"] == "healthy"
