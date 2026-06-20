# SYNC-022N HO Database Update Executor Installer

from pathlib import Path

code = '''
import pyodbc

class HoDatabaseUpdateExecutor:

    def execute(
        self,
        connection_string,
        sql,
        params
    ):
        connection = pyodbc.connect(
            connection_string
        )

        try:
            cursor = connection.cursor()

            cursor.execute(
                sql,
                params
            )

            rows_affected = cursor.rowcount

            connection.commit()

            return rows_affected

        finally:
            connection.close()
'''
test_code = '''
from store_agent.ho_database_update_executor import (
    HoDatabaseUpdateExecutor
)

def test_executor_exists():
    executor = HoDatabaseUpdateExecutor()
    assert executor is not None
'''

root = Path(r"E:\Nexora")

(root / "store_agent").mkdir(parents=True, exist_ok=True)
(root / "tests").mkdir(parents=True, exist_ok=True)

(root / "store_agent" / "ho_database_update_executor.py").write_text(
    code,
    encoding="utf-8"
)

(root / "tests" / "test_ho_database_update_executor.py").write_text(
    test_code,
    encoding="utf-8"
)

print("SYNC-022N INSTALL COMPLETE")
