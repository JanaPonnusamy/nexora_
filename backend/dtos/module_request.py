
from pydantic import BaseModel

class ModuleRequest(BaseModel):
    module_code: str
    module_name: str
    description: str | None = None

class ModuleStatusRequest(BaseModel):
    is_active: bool
