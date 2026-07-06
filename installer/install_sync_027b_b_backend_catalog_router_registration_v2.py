
from pathlib import Path
import shutil

candidates = [
    Path(r"E:\Nexora\backend\app.py"),
    Path(r"E:\Nexora\backend\main.py"),
]

APP = None

for candidate in candidates:
    if candidate.exists():
        APP = candidate
        break

if APP is None:
    raise FileNotFoundError(
        "backend app.py/main.py not found"
    )

backup = APP.parent / (APP.name + ".sync027b_b.bak")

if not backup.exists():
    shutil.copy2(APP, backup)

text = APP.read_text(encoding="utf-8")

import_line = """
from modules.sync.catalog_router import (
    router as catalog_router
)
"""

if "router as catalog_router" not in text:
    marker = "from modules.sync.table_registry_router import router as table_registry_router"
    text = text.replace(
        marker,
        marker + "\n" + import_line
    )

if "catalog_router" not in text.split("app.include_router")[-1]:
    marker = "app.include_router(table_registry_router)"
    text = text.replace(
        marker,
        marker + "\napp.include_router(catalog_router)",
        1
    )

APP.write_text(text, encoding="utf-8")

print(f"PATCHED: {APP}")
