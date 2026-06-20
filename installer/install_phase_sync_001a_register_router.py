# installer/install_phase_sync_001a_register_router.py

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

APP_FILE = ROOT / "backend" / "api" / "app.py"


def backup_file(path: Path):
    backup_dir = ROOT / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)


backup_file(APP_FILE)

content = APP_FILE.read_text(encoding="utf-8")

import_line = (
    "from modules.sync.router import router as sync_router"
)

include_line = (
    "app.include_router(sync_router)"
)

if import_line not in content:
    marker = (
        "from controllers.role_module_access_controller "
        "import router as role_module_access_router"
    )

    content = content.replace(
        marker,
        marker + "\n" + import_line
    )

if include_line not in content:
    marker = "app.include_router(role_module_access_router)"

    content = content.replace(
        marker,
        marker + "\n" + include_line
    )

APP_FILE.write_text(content, encoding="utf-8")

print("=" * 80)
print("SYNC ROUTER REGISTERED")
print("=" * 80)

print()
print("RUN")
print(r"cd E:\Nexora\backend")
print(r"python -m uvicorn api.app:app --reload")