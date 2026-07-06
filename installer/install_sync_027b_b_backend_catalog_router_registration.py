
from pathlib import Path
import shutil

APP = Path(r"E:\Nexora\backend\app.py")

backup = APP.with_suffix(".sync027b_b.bak")

if not backup.exists():
    shutil.copy2(APP, backup)

text = APP.read_text(encoding="utf-8")

import_line = """
from modules.sync.catalog_router import (
    router as catalog_router
)
"""

if "catalog_router" not in text:
    marker = "from modules.sync.table_registry_router import router as table_registry_router"
    text = text.replace(marker, marker + "\n" + import_line)

include_line = """
app.include_router(
    catalog_router
)
"""

if "app.include_router(\n    catalog_router" not in text:
    marker = "app.include_router(table_registry_router)"
    text = text.replace(marker, marker + "\n" + include_line, 1)

APP.write_text(text, encoding="utf-8")

print("SYNC-027B-B INSTALL COMPLETE")
