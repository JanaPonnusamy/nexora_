
from pydantic import BaseModel

class TenantRequest(BaseModel):
    tenant_code: str
    tenant_abbreviation: str
    tenant_name: str
    db_name: str

class TenantStatusRequest(BaseModel):
    is_active: bool
