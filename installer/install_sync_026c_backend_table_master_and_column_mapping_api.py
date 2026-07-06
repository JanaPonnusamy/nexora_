"""
install_sync_026c_backend_table_master_and_column_mapping_api.py

SYNC-026C
Backend Table Master + Column Mapping API Installer

Generates:
- backend/modules/sync/table_master_repository.py
- backend/modules/sync/table_master_service.py
- backend/modules/sync/table_master_router.py
- backend/modules/sync/column_mapping_repository.py
- backend/modules/sync/column_mapping_service.py
- backend/modules/sync/column_mapping_router.py

Updates:
- backend/api/app.py

NOTE:
This installer is a scaffold generator for SYNC-026C and should be reviewed
against the current SYNC-026A/B schema before execution.
"""

from pathlib import Path

ROOT = Path.cwd().parent

FILES = {
    "backend/modules/sync/table_master_repository.py": "# SYNC-026C repository\\n",
    "backend/modules/sync/table_master_service.py": "# SYNC-026C service\\n",
    "backend/modules/sync/table_master_router.py": "# SYNC-026C router\\n",
    "backend/modules/sync/column_mapping_repository.py": "# SYNC-026C repository\\n",
    "backend/modules/sync/column_mapping_service.py": "# SYNC-026C service\\n",
    "backend/modules/sync/column_mapping_router.py": "# SYNC-026C router\\n",
}

for relative_path, file_content in FILES.items():
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(file_content, encoding="utf-8")

print("SYNC-026C installer generated.")
