from fastapi import APIRouter, HTTPException
from .config_service import get_configuration

router = APIRouter(prefix='/api/store-agent', tags=['Store Agent'])

@router.get('/config/{store_id}')
def get_config(store_id:str):
    result = get_configuration(store_id)
    if not result:
        raise HTTPException(status_code=404, detail='Store not found')
    return result
