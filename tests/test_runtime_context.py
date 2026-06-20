from store_agent.runtime_context import StoreAgentRuntimeContext

def test_runtime_context_exists():

    ctx = StoreAgentRuntimeContext({})

    assert ctx is not None
