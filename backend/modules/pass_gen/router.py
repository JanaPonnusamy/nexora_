"""Pass Gen API — generates the legacy 14-character store passcodes.

Generation only: the old tool's validator is intentionally not exposed.
"""

from typing import List, Optional

from fastapi import APIRouter

from modules.pass_gen import service
from modules.pass_gen.schemas import (
    GenerateRequest,
    GenerateResponse,
    PassGenStore,
    StoreCodeInput,
)

router = APIRouter(prefix="/api/pass-gen", tags=["Pass Gen"])


@router.get("/stores", response_model=List[PassGenStore])
def list_stores(tenant_id: Optional[str] = None):
    """Active stores plus the numeric store code each one uses in a passcode."""
    return service.list_stores(tenant_id)


@router.put("/stores/{store_id}/code", response_model=List[PassGenStore])
def set_store_code(store_id: str, payload: StoreCodeInput):
    return service.set_store_code(store_id, payload.numeric_code)


@router.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest):
    return service.generate(payload)
