from fastapi import APIRouter

from .service import register_schema
from typing import List, Dict, Any
router = APIRouter(
    prefix="/api/sync/schema",
    tags=["Sync Schema"]
)


from typing import List, Dict, Any


@router.post("/register")
def schema_register(
    payload: List[Dict[str, Any]]
):
    return register_schema(payload)