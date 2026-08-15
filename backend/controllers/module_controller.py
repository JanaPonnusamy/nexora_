
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from services.module_service import ModuleService
from dtos.module_request import ModuleRequest, ModuleStatusRequest
from dependencies.auth import get_current_user
from modules.audit.writer import record_audit
from modules.audit.diff import compute_mutation_diff
from modules.audit.context import AuditContext

router = APIRouter(prefix='/api/modules', tags=['Modules'])

@router.post('/seed')
def seed_modules(request: Request, current_user: dict = Depends(get_current_user)):
    count = ModuleService().seed_modules()
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="module.seed",
        category="module",
        target_type="modules",
        reason=f"Seeded default system modules ({count} created)",
        metadata={"modules_created": count},
    )
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
def create_module(body: ModuleRequest, request: Request, current_user: dict = Depends(get_current_user)):
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
    res = ModuleService().get_by_id(str(new_id))

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="module.create",
        target_type="module",
        target_id=str(new_id),
        target_label=f"{module_name} ({module_code})",
        reason=f"Created module '{module_name}' ({module_code})",
        metadata={"module_code": module_code, "module_name": module_name, "description": description},
    )
    return res

@router.put('/{module_id}')
def update_module(module_id:str, body: ModuleRequest, request: Request, current_user: dict = Depends(get_current_user)):
    module_code = body.module_code.strip()
    module_name = body.module_name.strip()
    if not module_code:
        raise HTTPException(status_code=400, detail='Module code is required')
    if not module_name:
        raise HTTPException(status_code=400, detail='Module name is required')
    existing = ModuleService().get_by_id(module_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Module not found')
    if ModuleService().module_code_exists(module_code, module_id):
        raise HTTPException(status_code=400, detail='Module code already exists')
    description = body.description.strip() if body.description else None

    changed_fields, diff_details = compute_mutation_diff(
        dict(existing) if isinstance(existing, dict) else {},
        {"module_code": module_code, "module_name": module_name, "description": description},
    )
    changed_str = ", ".join(changed_fields) if changed_fields else "no field changes"

    ModuleService().update(module_id, module_code, module_name, description)
    res = ModuleService().get_by_id(module_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="module.update",
        target_type="module",
        target_id=module_id,
        target_label=f"{module_name} ({module_code})",
        reason=f"Updated module '{module_name}' (changed: {changed_str})",
        metadata={"diff": diff_details, "changed_fields": changed_fields},
    )
    return res

@router.patch('/{module_id}/status')
def set_module_status(module_id:str, body: ModuleStatusRequest, request: Request, current_user: dict = Depends(get_current_user)):
    existing = ModuleService().get_by_id(module_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Module not found')
    ModuleService().set_active(module_id, body.is_active)
    res = ModuleService().get_by_id(module_id)

    verb = "Activated" if body.is_active else "Deactivated"
    name = existing.get("module_name", module_id) if isinstance(existing, dict) else module_id
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="module.status.update",
        target_type="module",
        target_id=module_id,
        target_label=str(name),
        reason=f"{verb} module '{name}'",
        metadata={"is_active": body.is_active},
    )
    return res
