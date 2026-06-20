# SAVE AS:
# E:\Nexora\installer\install_sync_025b_a_backend_bulk_schema_registration.py

from pathlib import Path
import shutil
import textwrap

ROOT = Path(r"E:\Nexora")
BACKEND = ROOT / "backend"

FILES = {}

FILES[str(BACKEND / "modules" / "sync" / "repository.py")] = r'''
from config.database import get_connection


def bulk_register_schema_catalog(rows):
    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT schema_name,
                   table_name,
                   column_name
            FROM sync.sync_schema_catalog
            """
        )

        existing_rows = {
            (
                r.schema_name,
                r.table_name,
                r.column_name
            ): True
            for r in cursor.fetchall()
        }

        insert_rows = []
        update_rows = []

        for row in rows:

            key = (
                row["schema_name"],
                row["table_name"],
                row["column_name"]
            )

            if key in existing_rows:

                update_rows.append(
                    (
                        row.get("data_type"),
                        row.get("max_length"),
                        row.get("numeric_precision"),
                        row.get("numeric_scale"),
                        row.get("is_nullable"),
                        row.get("ordinal_position"),
                        row.get("source_database"),
                        row["schema_name"],
                        row["table_name"],
                        row["column_name"]
                    )
                )

            else:

                insert_rows.append(
                    (
                        row.get("source_database"),
                        row["schema_name"],
                        row["table_name"],
                        row["column_name"],
                        row.get("data_type"),
                        row.get("max_length"),
                        row.get("numeric_precision"),
                        row.get("numeric_scale"),
                        row.get("is_nullable"),
                        row.get("ordinal_position")
                    )
                )

        if insert_rows:

            cursor.executemany(
                """
                INSERT INTO sync.sync_schema_catalog
                (
                    source_database,
                    schema_name,
                    table_name,
                    column_name,
                    data_type,
                    max_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable,
                    ordinal_position
                )
                VALUES
                (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                insert_rows
            )

        if update_rows:

            cursor.executemany(
                """
                UPDATE sync.sync_schema_catalog
                   SET data_type = ?,
                       max_length = ?,
                       numeric_precision = ?,
                       numeric_scale = ?,
                       is_nullable = ?,
                       ordinal_position = ?,
                       source_database = ?
                 WHERE schema_name = ?
                   AND table_name = ?
                   AND column_name = ?
                """,
                update_rows
            )

        conn.commit()

        return {
            "inserted": len(insert_rows),
            "updated": len(update_rows),
            "total": len(rows)
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
'''

FILES[str(BACKEND / "modules" / "sync" / "service.py")] = r'''
from modules.sync.repository import (
    bulk_register_schema_catalog
)


def register_schema_catalog(payload):

    rows = []

    for row in payload.columns:

        rows.append(
            {
                "source_database": getattr(
                    row,
                    "source_database",
                    None
                ),
                "schema_name": row.schema_name,
                "table_name": row.table_name,
                "column_name": row.column_name,
                "data_type": getattr(
                    row,
                    "data_type",
                    None
                ),
                "max_length": getattr(
                    row,
                    "max_length",
                    None
                ),
                "numeric_precision": getattr(
                    row,
                    "numeric_precision",
                    None
                ),
                "numeric_scale": getattr(
                    row,
                    "numeric_scale",
                    None
                ),
                "is_nullable": getattr(
                    row,
                    "is_nullable",
                    None
                ),
                "ordinal_position": getattr(
                    row,
                    "ordinal_position",
                    None
                )
            }
        )

    return bulk_register_schema_catalog(rows)
'''

def backup_file(path: Path):
    if path.exists():
        backup = path.with_suffix(path.suffix + ".sync025b_a.bak")
        shutil.copy2(path, backup)


def write_file(path_str: str, content: str):
    path = Path(path_str)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    backup_file(path)

    path.write_text(
        textwrap.dedent(content).strip() + "\n",
        encoding="utf-8"
    )

    print(f"[UPDATED] {path}")


def main():

    print("=" * 80)
    print("SYNC-025B-A")
    print("Backend Bulk Schema Registration")
    print("=" * 80)

    for file_path, content in FILES.items():
        write_file(file_path, content)

    print()
    print("[SUCCESS]")
    print("repository.py updated")
    print("service.py updated")
    print("single connection")
    print("single transaction")
    print("single commit")
    print("bulk executemany enabled")


if __name__ == "__main__":
    main()