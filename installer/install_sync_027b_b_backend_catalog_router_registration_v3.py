
from pathlib import Path
import shutil

APP = Path(r"E:\Nexora\backend\api\app.py")

if not APP.exists():
    raise FileNotFoundError(str(APP))

backup = APP.parent / (APP.name + ".sync027b_b.bak")

if not backup.exists():
    shutil.copy2(APP, backup)

text = APP.read_text(encoding="utf-8")

import_block = """
from modules.sync.catalog_router import (
    router as catalog_router
)
"""

if "router as catalog_router" not in text:
    marker = "from modules.sync.table_registry_router import router as table_registry_router"
    text = text.replace(marker, marker + "\n" + import_block)

if "app.include_router(catalog_router)" not in text:
    marker = "app.include_router(table_registry_router)"
    text = text.replace(
        marker,
        marker + "\napp.include_router(catalog_router)",
        1
    )

APP.write_text(text, encoding="utf-8")

print("PATCHED:", APP)
