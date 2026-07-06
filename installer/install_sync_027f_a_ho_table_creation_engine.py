from pathlib import Path

ROOT = Path(r'E:\Nexora')
SYNC_DIR = ROOT / 'backend' / 'modules' / 'sync'
SYNC_DIR.mkdir(parents=True, exist_ok=True)

(SYNC_DIR / 'table_creation_repository.py').write_text('''from config.database import get_connection

def get_active_tables():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT sync_table_id, table_name FROM sync.sync_table_master WHERE is_active=1 ORDER BY sync_order")
        return cur.fetchall()
    finally:
        conn.close()

def get_table_columns(table_name):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name,data_type FROM sync.sync_column_mapping WHERE table_name=? AND is_selected=1 ORDER BY column_order", (table_name,))
        return cur.fetchall()
    finally:
        conn.close()
''', encoding='utf-8')

(SYNC_DIR / 'table_creation_service.py').write_text('''from .table_creation_repository import get_active_tables, get_table_columns

class TableCreationService:

    def build(self):
        result = []
        for row in get_active_tables():
            result.append({
                'table_name': row[1],
                'columns': get_table_columns(row[1])
            })
        return result
''', encoding='utf-8')

(SYNC_DIR / 'table_creation_router.py').write_text('''from fastapi import APIRouter
from .table_creation_service import TableCreationService

router = APIRouter(prefix='/api/sync/table-creation', tags=['Sync Table Creation'])

@router.post('/build/{execution_id}')
def build_tables(execution_id:str):
    return {
        'execution_id': execution_id,
        'tables': TableCreationService().build()
    }
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_table_creation_engine.py').write_text('''from modules.sync.table_creation_service import TableCreationService

def test_table_creation_service():
    assert TableCreationService() is not None
''', encoding='utf-8')

print('SYNC-027F-A INSTALL COMPLETE')
