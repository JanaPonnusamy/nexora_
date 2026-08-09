"""Pass Gen API — generates the legacy 14-character store passcodes.

Generation only: the old tool's validator is intentionally not exposed.
Every endpoint operates across ALL tenants' stores by design (it's a
platform-ops tool, not a tenant-facing screen), so it's restricted to super
admin / platform users only rather than tenant-scoped like the rest of the
API.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from dependencies.auth import get_current_user
from dependencies.store_scope import has_unrestricted_scope
from modules.pass_gen import service
from modules.pass_gen.schemas import (
    GenerateRequest,
    GenerateResponse,
    PassGenStore,
    StoreCodeInput,
)

router = APIRouter(prefix="/api/pass-gen", tags=["Pass Gen"])


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not has_unrestricted_scope(current_user):
        raise HTTPException(status_code=403, detail="Pass Gen is restricted to platform admins.")
    return current_user


@router.get("/stores", response_model=List[PassGenStore])
def list_stores(tenant_id: Optional[str] = None, current_user: dict = Depends(require_admin)):
    """Active stores plus the numeric store code each one uses in a passcode."""
    return service.list_stores(tenant_id)


@router.put("/stores/{store_id}/code", response_model=List[PassGenStore])
def set_store_code(store_id: str, payload: StoreCodeInput, current_user: dict = Depends(require_admin)):
    return service.set_store_code(store_id, payload.numeric_code)


@router.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest, current_user: dict = Depends(require_admin)):
    return service.generate(payload)
