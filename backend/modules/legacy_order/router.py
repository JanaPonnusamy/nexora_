"""Legacy Order console API.

A web trigger for the two buttons of the old VB.NET OrderManagement app: Sync
and Order Process. Everything here reads and writes the OLD OrderNMC database
and the branch DBs it points at -- NOT NEXORA_PLATFORM's sync.* tables.
"""
from fastapi import APIRouter, HTTPException

from modules.legacy_order import repository, service, sync_engine
from modules.legacy_order.schemas import JobStarted, OrderProcessRequest, SyncRequest

router = APIRouter(prefix="/api/legacy-order", tags=["Legacy Order"])


@router.get("/stores")
def list_stores(active_only: bool = True):
    """Branches from OrderNMC.Stores. Credentials are never returned."""
    stores = repository.list_stores(active_only)
    return [
        {
            "store_code": s["store_code"],
            "store_name": s["store_name"],
            "server_name": s["server_name"],
            "database": s["database"],
            "is_active": s["is_active"],
            "last_sync_time": s["last_sync_time"],
            "last_sync_status": s["last_sync_status"],
        }
        for s in stores
    ]


@router.get("/tables")
def list_tables():
    return [
        {"source": src, "destination": dest} for src, dest in sync_engine.TABLE_PLAN
    ]


@router.get("/defaults")
def defaults():
    return {"min_days": service.DEFAULT_MIN_DAYS, "max_days": service.DEFAULT_MAX_DAYS}


@router.post("/sync", response_model=JobStarted)
def start_sync(payload: SyncRequest):
    try:
        return JobStarted(job_id=service.start_sync(payload.store_name, payload.tables))
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/order-process", response_model=JobStarted)
def start_order_process(payload: OrderProcessRequest):
    try:
        job_id = service.start_order_process(
            payload.store_name, payload.min_days, payload.max_days, payload.mode
        )
        return JobStarted(job_id=job_id)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/jobs")
def list_jobs(limit: int = 20):
    return service.list_jobs(limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/orders/{store_name}")
def order_summary(store_name: str):
    """The current OrderManagement rows for a store -- the VB main grid."""
    return repository.order_summary(store_name)
