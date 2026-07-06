from pathlib import Path
import shutil

ROOT = Path(r'E:\Nexora')
SYNC_DIR = ROOT / 'backend' / 'modules' / 'sync'
SYNC_DIR.mkdir(parents=True, exist_ok=True)

(SYNC_DIR / 'ddl_creation_repository.py').write_text("""from config.database import get_connection

def get_tables():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT sync_table_id, table_name FROM sync.sync_table_master WHERE is_active=1 ORDER BY sync_order')
        return cur.fetchall()
    finally:
        conn.close()

def get_columns(table_name):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT column_name, data_type FROM sync.sync_column_mapping WHERE table_name=? AND is_selected=1 ORDER BY column_order',(table_name,))
        return cur.fetchall()
    finally:
        conn.close()

def execute_sql(sql):
    conn = get_connection()
    try:
        conn.cursor().execute(sql)
        conn.commit()
    finally:
        conn.close()
""", encoding='utf-8')

(SYNC_DIR / 'ddl_creation_service.py').write_text("""from .ddl_creation_repository import get_tables, get_columns, execute_sql

class DDLCreationService:

    def run(self):
        execute_sql("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name='tenant_data') EXEC('CREATE SCHEMA tenant_data')")

        tables_created = 0
        columns_created = 0

        for row in get_tables():
            table_name = row[1]

            execute_sql(f\"IF OBJECT_ID('tenant_data.{table_name}','U') IS NULL CREATE TABLE tenant_data.{table_name}(id BIGINT IDENTITY(1,1))\")

            tables_created += 1

            for col in get_columns(table_name):
                column_name = col[0]

                execute_sql(f\"IF COL_LENGTH('tenant_data.{table_name}','{column_name}') IS NULL ALTER TABLE tenant_data.{table_name} ADD [{column_name}] VARCHAR(500) NULL\")

                columns_created += 1

        return {
            'schema':'tenant_data',
            'tables_created':tables_created,
            'columns_created':columns_created,
            'status':'SUCCESS'
        }
""", encoding='utf-8')

(SYNC_DIR / 'ddl_creation_router.py').write_text("""from fastapi import APIRouter
from .ddl_creation_service import DDLCreationService

router = APIRouter(prefix='/api/sync/ddl', tags=['Sync DDL'])

@router.post('/build')
def build():
    return DDLCreationService().run()
""", encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_ddl_creation_engine.py').write_text("""def test_import():
    from backend.modules.sync.ddl_creation_service import DDLCreationService
    assert DDLCreationService is not None
""", encoding='utf-8')

print('SYNC-027F-C INSTALL COMPLETE')
