from store_agent.runtime_context_factory import RuntimeContextFactory

def test_runtime_context_factory():

    factory = RuntimeContextFactory()

    ctx = factory.create({})

    assert ctx is not None
