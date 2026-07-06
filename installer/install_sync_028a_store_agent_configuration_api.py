from pathlib import Path
import shutil

ROOT = Path(r'E:\Nexora')

MODULE_DIR = ROOT / 'backend' / 'modules' / 'store_agent'
MODULE_DIR.mkdir(parents=True, exist_ok=True)

(MODULE_DIR / 'config_repository.py').write_text('''from config.database import get_connection

def get_store_configuration(store_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT store_id,tenant_id,store_code,store_name,
            server_name,database_name,username,password_encrypted,
            connection_type,is_active
            FROM dbo.stores
            WHERE store_id=? AND is_active=1""",
            (store_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols,row))
    finally:
        conn.close()
''', encoding='utf-8')

(MODULE_DIR / 'config_service.py').write_text('''from .config_repository import get_store_configuration

def get_configuration(store_id):
    return get_store_configuration(store_id)
''', encoding='utf-8')

(MODULE_DIR / 'config_router.py').write_text('''from fastapi import APIRouter, HTTPException
from .config_service import get_configuration

router = APIRouter(prefix='/api/store-agent', tags=['Store Agent'])

@router.get('/config/{store_id}')
def get_config(store_id:str):
    result = get_configuration(store_id)
    if not result:
        raise HTTPException(status_code=404, detail='Store not found')
    return result
''', encoding='utf-8')

APP = ROOT / 'backend' / 'api' / 'app.py'
if APP.exists():
    backup = APP.parent / (APP.name + '.sync028a.bak')
    if not backup.exists():
        shutil.copy2(APP, backup)

(TESTS := ROOT / 'tests').mkdir(exist_ok=True)
(TESTS / 'test_store_agent_config_api.py').write_text('''def test_import():
    from backend.modules.store_agent.config_service import get_configuration
    assert get_configuration is not None
''', encoding='utf-8')

print('SYNC-028A INSTALL COMPLETE')
