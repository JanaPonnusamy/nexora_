# SYNC-016 Runtime Configuration Validation Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync016_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"CREATED : {path}")

validator_code = '''
class ConfigurationValidator:

    def validate(self, config):
        required = [
            "SQL_SERVER",
            "SQL_DATABASE",
            "STORE_ID",
            "HO_API_URL"
        ]

        return all(k in config for k in required)
'''

test_code = '''
from store_agent.configuration_validator import ConfigurationValidator

def test_configuration_validator():
    validator = ConfigurationValidator()

    assert validator.validate({
        "SQL_SERVER":"X",
        "SQL_DATABASE":"Y",
        "STORE_ID":"Z",
        "HO_API_URL":"A"
    }) is True
'''

write_file(ROOT / "store_agent" / "configuration_validator.py", validator_code)
write_file(ROOT / "tests" / "test_configuration_validator.py", test_code)

print("=" * 80)
print("SYNC-016 INSTALL COMPLETE")
print("=" * 80)
