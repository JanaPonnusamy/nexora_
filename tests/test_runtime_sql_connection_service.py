
from store_agent.runtime_sql_connection_service import (
    RuntimeSqlConnectionService
)

def test_runtime_sql_connection_service_exists():
    service = RuntimeSqlConnectionService()
    assert service is not None
