# installer/install_phase_sync_001_schema_register_api.py

"""
SYNC-001
Schema Register API Installer

Creates:

backend/modules/sync/__init__.py
backend/modules/sync/schemas.py
backend/modules/sync/repository.py
backend/modules/sync/service.py
backend/modules/sync/router.py
tests/test_sync_schema_register.py

Registers:

POST /api/sync/schema/register
"""

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")


def backup_file(path: Path):
    if not path.exists():
        return

    backup_dir = ROOT / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        path,
        backup_dir / path.name
    )


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        backup_file(path)

    path.write_text(content, encoding="utf-8")

    print(f"CREATED : {path}")


FILES = {}

FILES["backend/modules/sync/__init__.py"] = '''
'''

FILES["backend/modules/sync/schemas.py"] = '''
from pydantic import BaseModel
from typing import List, Optional


class ColumnSchema(BaseModel):
    column_name: str
    data_type: str
    max_length: Optional[int] = None
    precision_value: Optional[int] = None
    scale_value: Optional[int] = None
    is_nullable: bool
    is_identity: bool
    is_primary_key: bool
    ordinal_position: int


class TableSchema(BaseModel):
    schema_name: str
    table_name: str
    columns: List[ColumnSchema]


class SchemaRegisterRequest(BaseModel):
    store_id: str
    database_name: str
    tables: List[TableSchema]
'''

FILES["backend/modules/sync/repository.py"] = '''
from core.db import get_connection


def get_catalog_column(
    schema_name,
    table_name,
    column_name
):
    conn = get_connection()
    cur = conn.cursor()

    row = cur.execute("""
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
    ).fetchone()

    conn.close()

    return row


def insert_catalog_column(column):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
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
        column["is_nullable"],
        column["is_identity"],
        column["is_primary_key"],
        column["ordinal_position"]
    ))

    conn.commit()
    conn.close()


def update_catalog_column(column):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
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
        column["is_nullable"],
        column["is_identity"],
        column["is_primary_key"],
        column["ordinal_position"],
        column["schema_name"],
        column["table_name"],
        column["column_name"]
    ))

    conn.commit()
    conn.close()
'''

FILES["backend/modules/sync/service.py"] = '''
from .repository import (
    get_catalog_column,
    insert_catalog_column,
    update_catalog_column
)


def register_schema(payload):

    result = {
        "status": "success",
        "tables_processed": 0,
        "columns_processed": 0,
        "new_columns": 0,
        "updated_columns": 0
    }

    for table in payload.tables:

        result["tables_processed"] += 1

        for column in table.columns:

            result["columns_processed"] += 1

            row = {
                "schema_name": table.schema_name,
                "table_name": table.table_name,
                "column_name": column.column_name,
                "data_type": column.data_type,
                "max_length": column.max_length,
                "precision_value": column.precision_value,
                "scale_value": column.scale_value,
                "is_nullable": column.is_nullable,
                "is_identity": column.is_identity,
                "is_primary_key": column.is_primary_key,
                "ordinal_position": column.ordinal_position
            }

            exists = get_catalog_column(
                table.schema_name,
                table.table_name,
                column.column_name
            )

            if exists:
                update_catalog_column(row)
                result["updated_columns"] += 1
            else:
                insert_catalog_column(row)
                result["new_columns"] += 1

    return result
'''

FILES["backend/modules/sync/router.py"] = '''
from fastapi import APIRouter

from .schemas import SchemaRegisterRequest
from .service import register_schema

router = APIRouter(
    prefix="/api/sync/schema",
    tags=["Sync Schema"]
)


@router.post("/register")
def schema_register(
    payload: SchemaRegisterRequest
):
    return register_schema(payload)
'''

FILES["tests/test_sync_schema_register.py"] = '''
def test_sync_schema_register():
    assert True
'''


for relative_path, content in FILES.items():
    write_file(
        ROOT / relative_path,
        content.strip() + "\\n"
    )

print()
print("=" * 80)
print("SYNC-001 INSTALL COMPLETE")
print("=" * 80)

print()
print("RUN")
print(r"uvicorn main:app --reload")

print()
print("TEST")
print(r"pytest tests/test_sync_schema_register.py -v")