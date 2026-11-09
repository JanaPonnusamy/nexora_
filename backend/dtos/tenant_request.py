
from pydantic import BaseModel

class TenantRequest(BaseModel):
    tenant_code: str
    tenant_abbreviation: str
    tenant_name: str
    db_name: str
    # Central Legacy Order DB (OrderNMC/OrderSMS/...) for this tenant, on a
    # multi-tenant HO where each tenant keeps a separate one. Optional --
    # blank keeps using LEGACY_DB_DATABASE_BY_TENANT / the single-tenant
    # default (see modules/legacy_order/database.py).
    legacy_db_name: str | None = None

class TenantStatusRequest(BaseModel):
    is_active: bool
