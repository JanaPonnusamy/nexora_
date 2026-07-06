"""HTTP routing for the end-to-end Procurement pipeline + manual product search.

Mounted onto the module's main router (/api/procurement):
    POST /api/procurement/pipeline/run
    GET  /api/procurement/products/search
"""

from typing import Optional

from fastapi import APIRouter, Query

from modules.procurement import pipeline_service
from modules.procurement import platform_source_repository as src
from modules.procurement.pm_schemas import PipelineRun

router = APIRouter(tags=["Procurement Pipeline"])


@router.post("/pipeline/run")
def run_pipeline(payload: PipelineRun):
    """Run Sync → Cycle → Refresh → Decision Engine → VPL → Working Items on
    real synchronized data, and return the execution summary."""
    return pipeline_service.run(
        payload.tenant_id, payload.store_id, payload.rolling_days,
        payload.min_days, payload.max_days, payload.created_by,
    )


@router.get("/products/search")
def search_products(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    q: str = Query(""),
    limit: int = Query(25, ge=1, le=100),
):
    """Manual Add Product search over the real Product Master (code or name)."""
    return {"products": src.search_products(tenant_id, store_id, q, limit)}
