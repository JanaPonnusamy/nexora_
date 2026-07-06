"""HTTP routing for VPL comparison — Procurement Architecture Update.

Mounted onto the module's main `router` (prefix /api/procurement) BEFORE the
VPL router, so /vpl/compare resolves here rather than matching /vpl/{vpl_id}.
Comparison is a read-only runtime operation; nothing is persisted.
"""

from typing import Optional

from fastapi import APIRouter, Query

from modules.procurement import compare_service as service

router = APIRouter(prefix="/vpl", tags=["Procurement VPL Compare"])


@router.get("/compare")
def compare_vpls(
    source_vpl_id: str = Query(...),
    target_vpl_id: str = Query(...),
    tenant_id: str = Query(...),
    changed_only: bool = Query(False),
    action_filter: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return service.compare(
        tenant_id, source_vpl_id, target_vpl_id,
        changed_only, action_filter, search, page, page_size,
    )
