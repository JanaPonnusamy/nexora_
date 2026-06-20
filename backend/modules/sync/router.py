from fastapi import APIRouter

from .schemas import SchemaRegisterRequest
from .service import register_schema

router = APIRouter(
    prefix="/api/sync/schema",
    tags=["Sync Schema"]
)


@router.post("/register")
def schema_register(
    payload: SchemaRegisterRequest
):
    return register_schema(payload)