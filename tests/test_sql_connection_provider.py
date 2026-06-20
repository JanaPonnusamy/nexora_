from store_agent.sql_connection_provider import (
    SqlConnectionProvider
)

def test_provider_exists():

    provider = SqlConnectionProvider()

    assert provider is not None
