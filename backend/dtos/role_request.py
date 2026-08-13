
from __future__ import annotations

from pydantic import BaseModel

class RoleRequest(BaseModel):
    role_name: str
    description: str | None = None

class RoleStatusRequest(BaseModel):
    is_active: bool
