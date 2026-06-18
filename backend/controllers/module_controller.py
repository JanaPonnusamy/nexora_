
from fastapi import APIRouter, HTTPException
from services.module_service import ModuleService

router = APIRouter(prefix='/api/modules', tags=['Modules'])

@router.post('/seed')
def seed_modules():
    count = ModuleService().seed_modules()
    return {'status':'success','modules_created':count}

@router.get('')
def get_modules():
    return ModuleService().get_all()

@router.get('/{module_id}')
def get_module(module_id:str):

    module = ModuleService().get_by_id(module_id)

    if not module:
        raise HTTPException(status_code=404, detail='Module not found')

    return module
