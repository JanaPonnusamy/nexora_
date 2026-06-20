
from fastapi import APIRouter, HTTPException
from services.module_service import ModuleService
from dtos.module_request import ModuleRequest, ModuleStatusRequest

router = APIRouter(prefix='/api/modules', tags=['Modules'])

@router.post('/seed')
def seed_modules():
    count = ModuleService().seed_modules()
    return {'status':'success','modules_created':count}

@router.get('')
def get_modules(search: str | None = None, status: str | None = None):
    return ModuleService().get_all(search, status)

@router.get('/{module_id}')
def get_module(module_id:str):
    module = ModuleService().get_by_id(module_id)
    if not module:
        raise HTTPException(status_code=404, detail='Module not found')
    return module

@router.post('', status_code=201)
def create_module(body: ModuleRequest):
    module_code = body.module_code.strip()
    module_name = body.module_name.strip()
    if not module_code:
        raise HTTPException(status_code=400, detail='Module code is required')
    if not module_name:
        raise HTTPException(status_code=400, detail='Module name is required')
    if ModuleService().module_code_exists(module_code):
        raise HTTPException(status_code=400, detail='Module code already exists')
    description = body.description.strip() if body.description else None
    new_id = ModuleService().create(module_code, module_name, description)
    return ModuleService().get_by_id(str(new_id))

@router.put('/{module_id}')
def update_module(module_id:str, body: ModuleRequest):
    module_code = body.module_code.strip()
    module_name = body.module_name.strip()
    if not module_code:
        raise HTTPException(status_code=400, detail='Module code is required')
    if not module_name:
        raise HTTPException(status_code=400, detail='Module name is required')
    if not ModuleService().get_by_id(module_id):
        raise HTTPException(status_code=404, detail='Module not found')
    if ModuleService().module_code_exists(module_code, module_id):
        raise HTTPException(status_code=400, detail='Module code already exists')
    description = body.description.strip() if body.description else None
    ModuleService().update(module_id, module_code, module_name, description)
    return ModuleService().get_by_id(module_id)

@router.patch('/{module_id}/status')
def set_module_status(module_id:str, body: ModuleStatusRequest):
    if not ModuleService().get_by_id(module_id):
        raise HTTPException(status_code=404, detail='Module not found')
    ModuleService().set_active(module_id, body.is_active)
    return ModuleService().get_by_id(module_id)
