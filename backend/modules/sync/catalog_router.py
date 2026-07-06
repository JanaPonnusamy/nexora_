from fastapi import APIRouter
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
