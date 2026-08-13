
from __future__ import annotations

from pydantic import BaseModel

class StoreRequest(BaseModel):
    tenant_id: str
    store_code: str
    store_name: str
    server_name: str | None = None
    database_name: str | None = None

class StoreStatusRequest(BaseModel):
    is_active: bool
