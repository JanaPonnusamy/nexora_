# SYNC-021J SQL Connection Provider Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021J_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

provider_code = """
import pyodbc

from store_agent.sql_connection_factory import (
    SqlConnectionFactory
)

class SqlConnectionProvider:

    def get_connection(self, runtime_context):

        connection_string = (
            SqlConnectionFactory()
            .build_connection_string(runtime_context)
        )

        return pyodbc.connect(connection_string)
"""

test_code = """
from store_agent.sql_connection_provider import (
    SqlConnectionProvider
)

def test_provider_exists():

    provider = SqlConnectionProvider()

    assert provider is not None
"""

write_file(
    ROOT / "store_agent" / "sql_connection_provider.py",
    provider_code
)

write_file(
    ROOT / "tests" / "test_sql_connection_provider.py",
    test_code
)

print("SYNC-021J INSTALL COMPLETE")
