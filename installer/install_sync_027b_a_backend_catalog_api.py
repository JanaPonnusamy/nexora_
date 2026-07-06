
from pathlib import Path

ROOT = Path(r"E:\Nexora\backend\modules\sync")

(ROOT / "catalog_repository.py").write_text("""from config.database import get_connection

def get_sync_tables():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(\"\"\"
        SELECT sync_table_id,table_name,is_active,sync_mode,
               watermark_column,window_days,window_months,
               custom_where,sync_order,created_at
        FROM sync.sync_table_master
        WHERE is_active=1
        ORDER BY sync_order
        \"\"\")
        cols=[c[0] for c in cursor.description]
        return [dict(zip(cols,row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_sync_columns():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(\"\"\"
        SELECT mapping_id,sync_table_id,table_name,column_name,
               data_type,is_selected,is_pk,is_hash,
               is_watermark,column_order,created_at
        FROM sync.sync_column_mapping
        WHERE is_selected=1
        ORDER BY table_name,column_order
        \"\"\")
        cols=[c[0] for c in cursor.description]
        return [dict(zip(cols,row)) for row in cursor.fetchall()]
    finally:
        conn.close()
""", encoding="utf-8")

(ROOT / "catalog_service.py").write_text("""from .catalog_repository import get_sync_tables,get_sync_columns

def get_tables():
    return get_sync_tables()

def get_columns():
    return get_sync_columns()

def get_full_catalog():
    return {
        'tables': get_sync_tables(),
        'columns': get_sync_columns()
    }
""", encoding="utf-8")

(ROOT / "catalog_router.py").write_text("""from fastapi import APIRouter
from .catalog_service import get_tables,get_columns,get_full_catalog

router = APIRouter(
    prefix='/api/sync/catalog',
    tags=['Sync Catalog']
)

@router.get('/tables')
def tables():
    return get_tables()

@router.get('/columns')
def columns():
    return get_columns()

@router.get('/full')
def full():
    return get_full_catalog()
""", encoding="utf-8")

print("SYNC-027B-A INSTALL COMPLETE")
