# install_sync_026b_sync_table_master_promotion_engine.py

from pathlib import Path

ROOT = Path(r"E:\Nexora")

REPOSITORY_FILE = (
    ROOT
    / "backend"
    / "modules"
    / "sync"
    / "table_master_repository.py"
)

SERVICE_FILE = (
    ROOT
    / "backend"
    / "modules"
    / "sync"
    / "table_master_service.py"
)

ROUTER_FILE = (
    ROOT
    / "backend"
    / "modules"
    / "sync"
    / "table_master_router.py"
)

REPOSITORY_CODE = """
from config.database import get_connection


def promote_table_master():

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM dbo.sync_table_registry
            '''
        )

        registry_tables = cursor.fetchone()[0]

        cursor.execute(
            '''
            INSERT INTO sync.sync_table_master
            (
                sync_table_id,
                table_name,
                is_active,
                sync_mode,
                watermark_column,
                window_days,
                window_months,
                custom_where,
                sync_order,
                created_at
            )
            SELECT
                NEWID(),
                r.table_name,
                0,
                'UPSERT',
                NULL,
                NULL,
                NULL,
                NULL,
                r.sync_order,
                GETDATE()
            FROM dbo.sync_table_registry r
            LEFT JOIN sync.sync_table_master m
                ON m.table_name = r.table_name
            WHERE m.table_name IS NULL
            '''
        )

        promoted_tables = cursor.rowcount

        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM sync.sync_table_master
            '''
        )

        total_master_tables = cursor.fetchone()[0]

        conn.commit()

        return {
            "status": "success",
            "registry_tables": registry_tables,
            "promoted_tables": promoted_tables,
            "existing_tables": (
                registry_tables - promoted_tables
            ),
            "total_master_tables": total_master_tables
        }

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()
"""

SERVICE_CODE = """
from modules.sync.table_master_repository import (
    promote_table_master
)


def promote():

    return promote_table_master()
"""

ROUTER_CODE = """
from fastapi import APIRouter

from modules.sync.table_master_service import (
    promote
)

router = APIRouter(
    prefix="/api/sync/table-master",
    tags=["Sync Table Master"]
)


@router.post("/promote")
def promote_tables():

    return promote()
"""

for path in [
    REPOSITORY_FILE,
    SERVICE_FILE,
    ROUTER_FILE
]:

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

REPOSITORY_FILE.write_text(
    REPOSITORY_CODE.strip() + "\n",
    encoding="utf-8"
)

SERVICE_FILE.write_text(
    SERVICE_CODE.strip() + "\n",
    encoding="utf-8"
)

ROUTER_FILE.write_text(
    ROUTER_CODE.strip() + "\n",
    encoding="utf-8"
)

print()
print("=" * 80)
print("SYNC-026B")
print("Sync Table Master Promotion Engine")
print("=" * 80)

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

print(
    "Add import to api/app.py:"
)
print(
    "from modules.sync.table_master_router "
    "import router as table_master_router"
)

print()

print(
    "Add router registration:"
)
print(
    "app.include_router(table_master_router)"
)

print()
print("=" * 80)
print("INSTALL COMPLETE")
print("=" * 80)