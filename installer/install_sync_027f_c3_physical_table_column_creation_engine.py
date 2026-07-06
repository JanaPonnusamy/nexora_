from pathlib import Path

ROOT = Path(r"E:\Nexora")
SYNC_DIR = ROOT / "backend" / "modules" / "sync"
SYNC_DIR.mkdir(parents=True, exist_ok=True)

(SYNC_DIR / "physical_table_creation_repository.py").write_text("""from config.database import get_connection

def get_tables():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM sync.sync_table_master WHERE is_active=1 ORDER BY sync_order")
        return cur.fetchall()
    finally:
        conn.close()

def get_columns(table_name):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT column_name,data_type,is_pk FROM sync.sync_column_mapping WHERE table_name=? AND is_selected=1 ORDER BY column_order',(table_name,))
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
""", encoding="utf-8")

(SYNC_DIR / "physical_table_creation_service.py").write_text("""from .physical_table_creation_repository import get_tables,get_columns,execute_sql

class PhysicalTableCreationService:

    def run(self,schema_name):

        tables_created = 0
        columns_created = 0

        for row in get_tables():

            table_name = row[0]

            execute_sql(f\\"IF OBJECT_ID('{schema_name}.{table_name}','U') IS NULL CREATE TABLE [{schema_name}].[{table_name}] (sync_internal_id BIGINT IDENTITY(1,1))\\")

            tables_created += 1

            for col in get_columns(table_name):

                column_name = col[0]

                execute_sql(f\\"IF COL_LENGTH('{schema_name}.{table_name}','{column_name}') IS NULL ALTER TABLE [{schema_name}].[{table_name}] ADD [{column_name}] VARCHAR(500) NULL\\")

                columns_created += 1

        return {
            'schema':schema_name,
            'tables_created':tables_created,
            'columns_created':columns_created,
            'status':'SUCCESS'
        }
""", encoding="utf-8")

(SYNC_DIR / "physical_table_creation_router.py").write_text("""from fastapi import APIRouter
from .physical_table_creation_service import PhysicalTableCreationService

router = APIRouter(prefix='/api/sync/physical-ddl', tags=['Physical DDL'])

@router.post('/build/{tenant_guid}')
def build(tenant_guid:str):
    schema_name = f'tenant_{tenant_guid.replace("-","")[:8]}'
    return PhysicalTableCreationService().run(schema_name)
""", encoding="utf-8")

(ROOT / "tests").mkdir(exist_ok=True)

(ROOT / "tests" / "test_physical_table_creation.py").write_text("""def test_import():
    from backend.modules.sync.physical_table_creation_service import PhysicalTableCreationService
    assert PhysicalTableCreationService is not None
""", encoding="utf-8")

print('SYNC-027F-C3 INSTALL COMPLETE')
