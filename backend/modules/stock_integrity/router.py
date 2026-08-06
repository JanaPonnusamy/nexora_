"""Stock Integrity Verification API — read-only comparison report.

Phase 1: compares SUM(sync.Batches.Stock) against sync.Products.TotalStock
per store/product within NEXORA_PLATFORM only. No repair endpoint yet -- see
repository.py docstring for why the "batch sum is truth" assumption needs to
be checked against real mismatches before any write path is built.
"""

from fastapi import APIRouter, HTTPException

from modules.stock_integrity import service
from modules.stock_integrity.schemas import RepairResult, StockIntegrityResult, SyncDriftResult

router = APIRouter(prefix="/api/stock-integrity", tags=["Stock Integrity"])


@router.get("/report", response_model=StockIntegrityResult)
def get_report(tenant_id: str, store_id: str = ""):
    return service.get_integrity_report(tenant_id, store_id)


@router.get("/sync-drift", response_model=SyncDriftResult)
def get_sync_drift(tenant_id: str, store_id: str):
    """Live store DB vs synced sync.Batches, read-only against the branch server."""
    try:
        return service.get_sync_drift_report(tenant_id, store_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach store database: {exc}")


@router.post("/repair", response_model=RepairResult)
def repair(tenant_id: str, store_id: str, actor_user_id: str = ""):
    """One-time backlog repair of stale sync.Batches.Stock rows using live
    store data. See modules/stock_integrity/repository.py:repair_batch_stock
    for exactly what is and isn't touched."""
    try:
        return service.repair_store(tenant_id, store_id, actor_user_id or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Repair failed: {exc}")
