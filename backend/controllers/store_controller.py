from fastapi import APIRouter
from services.store_service import StoreService

router = APIRouter(
    prefix="/api/stores",
    tags=["Stores"]
)

@router.get("")
def get_stores():

    rows = StoreService().get_all()

    return [
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


@router.get("/tenant/{tenant_id}")
def get_by_tenant(tenant_id: str):

    rows = StoreService().get_by_tenant(
        tenant_id
    )

    return [
        {
            "store_id": str(r[0]),
            "store_code": r[2],
            "store_name": r[3]
        }
        for r in rows
    ]


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