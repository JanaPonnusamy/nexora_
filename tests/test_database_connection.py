from store_agent.database import get_connection

def test_database_module_exists():
    assert callable(get_connection)
