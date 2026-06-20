
from pydantic import BaseModel

class PermissionAssignRequest(BaseModel):
    role_id: str
    module_id: str
