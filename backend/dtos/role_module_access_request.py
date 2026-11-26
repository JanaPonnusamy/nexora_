
from __future__ import annotations

from pydantic import BaseModel

class RoleModuleAccessRequest(BaseModel):
    role_id: str
    module_id: str
    can_view: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_export: bool = False
