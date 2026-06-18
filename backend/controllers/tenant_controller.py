
from fastapi import APIRouter
from services.tenant_service import TenantService

router = APIRouter(prefix="/api/tenants", tags=["Tenants"])

@router.get("")
def get_tenants():
    rows = TenantService().get_all()
    return [{"tenant_id":str(r[0]),"tenant_code":r[1],"tenant_abbreviation":r[2],"tenant_name":r[3],"db_name":r[4],"is_active":bool(r[5])} for r in rows]

@router.get("/{tenant_id}")
def get_tenant(tenant_id:str):
    r = TenantService().get_by_id(tenant_id)
    if not r:
        return {"error":"Tenant Not Found"}
    return {"tenant_id":str(r[0]),"tenant_code":r[1],"tenant_abbreviation":r[2],"tenant_name":r[3],"db_name":r[4],"is_active":bool(r[5])}
