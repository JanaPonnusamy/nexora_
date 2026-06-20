# SYNC-021K SQL Server Validation Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021K_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

validator_code = """
class SqlServerValidator:

    def validate_version_text(self, version_text):

        if not version_text:
            return False

        return "Microsoft SQL Server" in version_text
"""

test_code = """
from store_agent.sql_server_validator import SqlServerValidator

def test_sql_server_validator():

    validator = SqlServerValidator()

    assert validator.validate_version_text(
        "Microsoft SQL Server 2014"
    ) is True
"""

write_file(
    ROOT / "store_agent" / "sql_server_validator.py",
    validator_code
)

write_file(
    ROOT / "tests" / "test_sql_server_validator.py",
    test_code
)

print("SYNC-021K INSTALL COMPLETE")
