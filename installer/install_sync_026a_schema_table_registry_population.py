# install_sync_026a_schema_table_registry_population.py

from pathlib import Path
import shutil

ROOT = Path(r"E:\Nexora")

REPOSITORY_FILE = (
    ROOT
    / "backend"
    / "modules"
    / "sync"
    / "table_registry_repository.py"
)

SERVICE_FILE = (
    ROOT
    / "backend"
    / "modules"
    / "sync"
    / "table_registry_service.py"
)

ROUTER_FILE = (
    ROOT
    / "backend"
    / "modules"
    / "sync"
    / "table_registry_router.py"
)

APP_FILE = (
    ROOT
    / "backend"
    / "api"
    / "app.py"
)

REPOSITORY_CODE = '''
from config.database import get_connection


def populate_table_registry():

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT table_name)
            FROM sync.sync_schema_catalog
            """
        )

        tables_discovered = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO dbo.sync_table_registry
            (
                tenant_id,
                table_name,
                sync_order,
                chunk_enabled,
                refresh_enabled,
                is_active
            )
            SELECT
                '00000000-0000-0000-0000-000000000000',
                src.table_name,
                999,
                1,
                1,
                1
            FROM
            (
                SELECT DISTINCT
                    table_name
                FROM sync.sync_schema_catalog
            ) src
            LEFT JOIN dbo.sync_table_registry trg
                ON trg.table_name = src.table_name
            WHERE trg.table_name IS NULL
            """
        )

        new_tables = cursor.rowcount

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dbo.sync_table_registry
            """
        )

        total_registry_tables = cursor.fetchone()[0]

        conn.commit()

        return {
            "status": "success",
            "tables_discovered": tables_discovered,
            "new_tables": new_tables,
            "existing_tables": (
                tables_discovered - new_tables
            ),
            "total_registry_tables": total_registry_tables
        }

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()
'''

SERVICE_CODE = '''
from modules.sync.table_registry_repository import (
    populate_table_registry
)


def populate_registry():

    return populate_table_registry()
'''

ROUTER_CODE = '''
from fastapi import APIRouter

from modules.sync.table_registry_service import (
    populate_registry
)

router = APIRouter(
    prefix="/api/sync/table-registry",
    tags=["Sync Table Registry"]
)


@router.post("/populate")
def populate():

    return populate_registry()
'''

print("=" * 80)
print("SYNC-026A")
print("Schema Table Registry Population")
print("=" * 80)

for file_path in [
    REPOSITORY_FILE,
    SERVICE_FILE,
    ROUTER_FILE
]:

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

REPOSITORY_FILE.write_text(
    REPOSITORY_CODE.strip() + "\\n",
    encoding="utf-8"
)

SERVICE_FILE.write_text(
    SERVICE_CODE.strip() + "\\n",
    encoding="utf-8"
)

ROUTER_FILE.write_text(
    ROUTER_CODE.strip() + "\\n",
    encoding="utf-8"
)

print()
print("[CREATED]")
print(REPOSITORY_FILE)

print()
print("[CREATED]")
print(SERVICE_FILE)

print()
print("[CREATED]")
print(ROUTER_FILE)

print()
print("MANUAL STEP")
print("-" * 80)
print("Add to api/app.py")
print()
print(
    "from modules.sync.table_registry_router "
    "import router as table_registry_router"
)
print()
print(
    "app.include_router("
    "table_registry_router)"
)

print()
print("=" * 80)
print("INSTALL COMPLETE")
print("=" * 80)

print()
print("RUN")
print(
    r"python install_sync_026a_schema_table_registry_population.py"
)

print()
print("TEST")
print(
    r'Invoke-RestMethod -Method POST '
    r'-Uri "http://127.0.0.1:8000/api/sync/table-registry/populate"'
)