
from store_agent.store_password_repository_update import (
    StorePasswordRepositoryUpdate
)

def test_build_update_command():

    repo = StorePasswordRepositoryUpdate()

    sql, params = repo.build_update_command(
        "STORE001",
        b"abc"
    )

    assert "UPDATE dbo.stores" in sql
    assert params[1] == "STORE001"
