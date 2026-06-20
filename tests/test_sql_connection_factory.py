from store_agent.sql_connection_factory import SqlConnectionFactory

def test_connection_factory_exists():

    factory = SqlConnectionFactory()

    assert factory is not None
