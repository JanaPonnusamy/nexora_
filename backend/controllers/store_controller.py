from fastapi import APIRouter, Depends, HTTPException
from services.store_service import StoreService
from dtos.store_request import StoreRequest, StoreStatusRequest
from dependencies.auth import get_current_user_optional
from dependencies.store_scope import has_unrestricted_scope

router = APIRouter(
    prefix="/api/stores",
    tags=["Stores"]
)

def _serialize(r):
    return {
        "store_id": str(r[0]),
        "tenant_id": str(r[1]),
        "store_code": r[2],
        "store_name": r[3],
        "server_name": r[4],
        "database_name": r[5],
        "is_active": bool(r[6]),
    }

@router.get("")
def get_stores(current_user: dict | None = Depends(get_current_user_optional)):

    rows = StoreService().get_all()

    stores = [
        {
            "store_id": str(r[0]),
            "tenant_id": str(r[1]),
            "store_code": r[2],
            "store_name": r[3],
            "server_name": r[4],
            "database_name": r[5],
            "is_active": bool(r[6])
        }
        for r in rows
    ]

    if has_unrestricted_scope(current_user):
        return stores

    # Non-broad users (purchase manager, salesman, any tenant-scoped role) only
    # see their own tenant's stores - Stock Availability is a network-wide
    # stock lookup, so any store within their own tenant is fair game, just
    # never another tenant's. Previously every store across every tenant was
    # returned to any authenticated user.
    own_tenant_id = str(current_user.get("tenant_id") or "")
    return [s for s in stores if s["tenant_id"] == own_tenant_id]


@router.get("/tenant/{tenant_id}")
def get_by_tenant(tenant_id: str, current_user: dict | None = Depends(get_current_user_optional)):

    if not has_unrestricted_scope(current_user) and str(current_user.get("tenant_id") or "") != str(tenant_id):
        raise HTTPException(status_code=403, detail="You do not have access to this tenant.")

    rows = StoreService().get_by_tenant(
        tenant_id
    )

    stores = [
        {
            "store_id": str(r[0]),
            "store_code": r[2],
            "store_name": r[3]
        }
        for r in rows
    ]

    # The tenant check above already rejected any tenant_id that isn't this
    # user's own (or let a super admin/platform user through), so every
    # store this query returns is already in-scope.
    return stores


@router.get("/{store_id}/agent-config")
def get_agent_config(store_id: str):

    row = StoreService().get_agent_config(
        store_id
    )

    if not row:
        return {
            "error": "Store Not Found"
        }

    return {
        "store_id": str(row[0]),
        "store_code": row[1],
        "server_name": row[2],
        "database_name": row[3],
        "username": row[4],
        "password_encrypted":
            row[5].hex()
            if row[5]
            else None,
        "connection_type": row[6],
        "agent_version": row[7],
        "is_active": bool(row[8])
    }


@router.get("/{store_id}")
def get_store(store_id: str):

    r = StoreService().get_by_id(store_id)

    if not r:
        return {
            "error": "Store Not Found"
        }

    return {
        "store_id": str(r[0]),
        "tenant_id": str(r[1]),
        "store_code": r[2],
        "store_name": r[3],
        "server_name": r[4],
        "database_name": r[5],
        "is_active": bool(r[6])
    }


@router.post("", status_code=201)
def create_store(body: StoreRequest):
    svc = StoreService()
    store_code = body.store_code.strip()
    store_name = body.store_name.strip()
    if not body.tenant_id.strip():
        raise HTTPException(status_code=400, detail="Tenant is required")
    if not store_code:
        raise HTTPException(status_code=400, detail="Store code is required")
    if not store_name:
        raise HTTPException(status_code=400, detail="Store name is required")
    if svc.store_code_exists(store_code, body.tenant_id):
        raise HTTPException(status_code=400, detail="Store code already exists for this tenant")
    new_id = svc.create(body.tenant_id, store_code, store_name, body.server_name, body.database_name)
    return _serialize(svc.get_by_id(str(new_id)))


@router.put("/{store_id}")
def update_store(store_id: str, body: StoreRequest):
    svc = StoreService()
    store_code = body.store_code.strip()
    store_name = body.store_name.strip()
    if not store_code:
        raise HTTPException(status_code=400, detail="Store code is required")
    if not store_name:
        raise HTTPException(status_code=400, detail="Store name is required")
    if not svc.get_by_id(store_id):
        raise HTTPException(status_code=404, detail="Store Not Found")
    if svc.store_code_exists(store_code, body.tenant_id, store_id):
        raise HTTPException(status_code=400, detail="Store code already exists for this tenant")
    svc.update(store_id, body.tenant_id, store_code, store_name, body.server_name, body.database_name)
    return _serialize(svc.get_by_id(store_id))


@router.patch("/{store_id}/status")
def set_store_status(store_id: str, body: StoreStatusRequest):
    svc = StoreService()
    if not svc.get_by_id(store_id):
        raise HTTPException(status_code=404, detail="Store Not Found")
    svc.set_active(store_id, body.is_active)
    return _serialize(svc.get_by_id(store_id))