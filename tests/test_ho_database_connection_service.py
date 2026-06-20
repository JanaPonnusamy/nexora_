
from store_agent.ho_database_connection_service import (
    HoDatabaseConnectionService
)

def test_ho_database_connection_service():

    service = HoDatabaseConnectionService()

    result = service.build_update_execution(
        "UPDATE dbo.stores",
        ("abc", "store1")
    )

    assert result["sql"] == "UPDATE dbo.stores"
