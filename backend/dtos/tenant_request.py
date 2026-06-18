
from pydantic import BaseModel

class TenantRequest(BaseModel):
    tenant_name: str
    tenant_code: str
