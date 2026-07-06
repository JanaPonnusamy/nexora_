from pathlib import Path

ROOT = Path(r'E:\Nexora')

SYNC_DIR = ROOT / 'backend' / 'modules' / 'sync'
SYNC_DIR.mkdir(parents=True, exist_ok=True)

(SYNC_DIR / 'ddl_executor_repository.py').write_text('''from config.database import get_connection

def execute_sql(sql):

    conn = get_connection()

    try:

        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

    finally:

        conn.close()
''', encoding='utf-8')

(SYNC_DIR / 'ddl_executor_service.py').write_text('''from .ddl_executor_repository import execute_sql

class DDLExecutorService:

    PLATFORM_COLUMNS = [
        ('tenant_id','UNIQUEIDENTIFIER NULL'),
        ('store_id','UNIQUEIDENTIFIER NULL'),
        ('execution_id','UNIQUEIDENTIFIER NULL'),
        ('row_hash','VARCHAR(32) NULL'),
        ('sync_created_at','DATETIME NULL'),
        ('sync_updated_at','DATETIME NULL')
    ]

    def execute(self, schema_name):

        execute_sql(
            f\"\"\"
IF NOT EXISTS (
SELECT 1
FROM sys.schemas
WHERE name='{schema_name}'
)
EXEC('CREATE SCHEMA [{schema_name}]')
\"\"\"
        )

        return {
            'success': True,
            'schema': schema_name
        }
''', encoding='utf-8')

(SYNC_DIR / 'ddl_executor_router.py').write_text('''from fastapi import APIRouter
from .ddl_executor_service import DDLExecutorService

router = APIRouter(
    prefix='/api/sync/ddl-executor',
    tags=['DDL Executor']
)

@router.post('/execute/{tenant_guid}')
def execute(tenant_guid:str):

    schema_name = f'tenant_{tenant_guid.replace("-","")[:8]}'

    return DDLExecutorService().execute(
        schema_name
    )
''', encoding='utf-8')

(ROOT / 'tests').mkdir(exist_ok=True)

(ROOT / 'tests' / 'test_ddl_executor.py').write_text('''def test_import():
    from backend.modules.sync.ddl_executor_service import DDLExecutorService
    assert DDLExecutorService is not None
''', encoding='utf-8')

print('SYNC-027F-C2 INSTALL COMPLETE')
