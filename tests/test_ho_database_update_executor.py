
from store_agent.ho_database_update_executor import (
    HoDatabaseUpdateExecutor
)

def test_executor_exists():
    executor = HoDatabaseUpdateExecutor()
    assert executor is not None
