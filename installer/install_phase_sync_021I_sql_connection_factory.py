# SYNC-021I SQL Connection Factory Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021I_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

factory_code = """
class SqlConnectionFactory:

    def build_connection_string(self, runtime_context):

        return (
            'DRIVER={ODBC Driver 17 for SQL Server};'
            f'SERVER={runtime_context.sql_server};'
            f'DATABASE={runtime_context.database_name};'
            f'UID={runtime_context.sql_username};'
            f'PWD={runtime_context.sql_password};'
            'TrustServerCertificate=yes;'
        )
"""

test_code = """
from store_agent.sql_connection_factory import SqlConnectionFactory

def test_connection_factory_exists():

    factory = SqlConnectionFactory()

    assert factory is not None
"""

write_file(
    ROOT / "store_agent" / "sql_connection_factory.py",
    factory_code
)

write_file(
    ROOT / "tests" / "test_sql_connection_factory.py",
    test_code
)

print("SYNC-021I INSTALL COMPLETE")
