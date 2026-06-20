# installer/install_phase_sync_001b_repair.py

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

FILES = [
    ROOT / "backend" / "modules" / "sync" / "__init__.py",
    ROOT / "backend" / "modules" / "sync" / "repository.py",
    ROOT / "backend" / "modules" / "sync" / "service.py",
    ROOT / "backend" / "modules" / "sync" / "schemas.py",
    ROOT / "backend" / "modules" / "sync" / "router.py",
]


def backup_file(path: Path):
    if not path.exists():
        return

    backup_dir = ROOT / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(path, backup_dir / path.name)


for file_path in FILES:
    if file_path.exists():
        backup_file(file_path)

# ------------------------------------------------------------------
# __init__.py
# ------------------------------------------------------------------

(ROOT / "backend/modules/sync/__init__.py").write_text(
    "",
    encoding="utf-8"
)

# ------------------------------------------------------------------
# repository.py
# ------------------------------------------------------------------

(ROOT / "backend/modules/sync/repository.py").write_text(
'''from config.database import get_connection


def get_catalog_column(
    schema_name,
    table_name,
    column_name
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT catalog_id
        FROM sync.sync_schema_catalog
        WHERE schema_name=?
          AND table_name=?
          AND column_name=?
        """,
        (
            schema_name,
            table_name,
            column_name
        )
    )

    row = cur.fetchone()

    conn.close()

    return row


def insert_catalog_column(column):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO sync.sync_schema_catalog
        (
            schema_name,
            table_name,
            column_name,
            data_type,
            max_length,
            precision_value,
            scale_value,
            is_nullable,
            is_identity,
            is_primary_key,
            ordinal_position,
            first_discovered_at,
            last_discovered_at,
            is_active
        )
        VALUES
        (
            ?,?,?,?,?,?,?,?,?,?,
            ?,GETDATE(),GETDATE(),1
        )
        """,
        (
            column["schema_name"],
            column["table_name"],
            column["column_name"],
            column["data_type"],
            column["max_length"],
            column["precision_value"],
            column["scale_value"],
            int(column["is_nullable"]),
            int(column["is_identity"]),
            int(column["is_primary_key"]),
            column["ordinal_position"]
        )
    )

    conn.commit()
    conn.close()


def update_catalog_column(column):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE sync.sync_schema_catalog
        SET
            data_type=?,
            max_length=?,
            precision_value=?,
            scale_value=?,
            is_nullable=?,
            is_identity=?,
            is_primary_key=?,
            ordinal_position=?,
            last_discovered_at=GETDATE()
        WHERE
            schema_name=?
            AND table_name=?
            AND column_name=?
        """,
        (
            column["data_type"],
            column["max_length"],
            column["precision_value"],
            column["scale_value"],
            int(column["is_nullable"]),
            int(column["is_identity"]),
            int(column["is_primary_key"]),
            column["ordinal_position"],
            column["schema_name"],
            column["table_name"],
            column["column_name"]
        )
    )

    conn.commit()
    conn.close()
''',
    encoding="utf-8"
)

print("=" * 80)
print("SYNC REPAIR COMPLETE")
print("=" * 80)

print()
print("VERIFY")
print(r"python -m py_compile E:\Nexora\backend\modules\sync\repository.py")
print(r"python -m py_compile E:\Nexora\backend\modules\sync\service.py")
print(r"python -m py_compile E:\Nexora\backend\modules\sync\schemas.py")
print(r"python -m py_compile E:\Nexora\backend\modules\sync\router.py")

print()
print("RUN")
print(r"cd E:\Nexora\backend")
print(r"python -m api.app")