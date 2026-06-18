
from fastapi import APIRouter
from services.store_service import StoreService

router = APIRouter(prefix="/api/stores", tags=["Stores"])

@router.get("")
def get_stores():
    rows = StoreService().get_all()
    return [{"store_id":str(r[0]),"tenant_id":str(r[1]),"store_code":r[2],"store_name":r[3],"server_name":r[4],"database_name":r[5],"is_active":bool(r[6])} for r in rows]

@router.get("/tenant/{tenant_id}")
def get_by_tenant(tenant_id:str):
    rows = StoreService().get_by_tenant(tenant_id)
    return [{"store_id":str(r[0]),"store_code":r[2],"store_name":r[3]} for r in rows]

@router.get("/{store_id}")
def get_store(store_id:str):
    r = StoreService().get_by_id(store_id)
    if not r:
        return {"error":"Store Not Found"}
    return {"store_id":str(r[0]),"tenant_id":str(r[1]),"store_code":r[2],"store_name":r[3],"server_name":r[4],"database_name":r[5],"is_active":bool(r[6])}
